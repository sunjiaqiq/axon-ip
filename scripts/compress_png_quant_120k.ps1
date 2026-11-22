param(
  [string]$DownloadsDir = 'D:\Documents\Downloads',
  # 用于定位你那张“(1).png”
  [long]$TargetPngSizeBytes = 395201,
  [long]$MaxPngSizeBytes = 120000
)

$png = Get-ChildItem -LiteralPath $DownloadsDir -Filter '*.png' |
  Where-Object { $_.Length -eq $TargetPngSizeBytes -and $_.Name -like '* (1).png' } |
  Select-Object -First 1

if(-not $png){
  throw "Target PNG not found. dir='$DownloadsDir' sizeBytes=$TargetPngSizeBytes"
}

$inPath = $png.FullName
$outPath = Join-Path $DownloadsDir (([System.IO.Path]::GetFileNameWithoutExtension($inPath)) + '_120k.png')

$bmp = $null

try {
  try {
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop | Out-Null
  } catch {
    Add-Type -AssemblyName System.Drawing.Common -ErrorAction Stop | Out-Null
  }

  $bmp = [System.Drawing.Bitmap]::FromFile($inPath)

  # 量化到 8bpp indexed PNG
  $cs = @"
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;

public static class PngQuantizer
{
  // Simple RGBA k-means quantizer, then output an 8bpp indexed bitmap.
  public static Bitmap QuantizeTo8bppIndexed(Bitmap src, int k, int sampleStep, int iterations, int seed)
  {
    int w = src.Width;
    int h = src.Height;

    // Ensure we can read pixels efficiently
    Bitmap src32 = new Bitmap(w, h, PixelFormat.Format32bppArgb);
    using (var g = Graphics.FromImage(src32))
      g.DrawImage(src, new Rectangle(0,0,w,h), new Rectangle(0,0,w,h), GraphicsUnit.Pixel);

    // Extract pixels
    var rect = new Rectangle(0,0,w,h);
    BitmapData data = src32.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
    int stride = data.Stride;
    int total = w * h;

    byte[] pixels = new byte[stride * h];
    System.Runtime.InteropServices.Marshal.Copy(data.Scan0, pixels, 0, pixels.Length);
    src32.UnlockBits(data);

    // Sample pixels
    List<int> sampleIdx = new List<int>();
    for(int y=0; y<h; y+=sampleStep){
      for(int x=0; x<w; x+=sampleStep){
        sampleIdx.Add(y*w + x);
      }
    }
    if(sampleIdx.Count == 0) sampleIdx.Add(0);

    // Centroids
    Random rnd = new Random(seed);
    double[] cr = new double[k];
    double[] cg = new double[k];
    double[] cb = new double[k];
    double[] ca = new double[k];

    // Correct pixel access: for a linear index p: x=p%w, y=p/w
    for(int i=0;i<k;i++){
      int p = sampleIdx[rnd.Next(sampleIdx.Count)];
      int x = p % w;
      int y = p / w;
      int off = y*stride + x*4;
      // Format32bppArgb in memory is BGRA
      cb[i] = pixels[off + 0];
      cg[i] = pixels[off + 1];
      cr[i] = pixels[off + 2];
      ca[i] = pixels[off + 3];
    }

    int[] counts = new int[k];
    double[] sr = new double[k];
    double[] sg = new double[k];
    double[] sb = new double[k];
    double[] sa = new double[k];

    // K-means iterations
    for(int it=0; it<iterations; it++){
      Array.Clear(counts, 0, k);
      Array.Clear(sr, 0, k);
      Array.Clear(sg, 0, k);
      Array.Clear(sb, 0, k);
      Array.Clear(sa, 0, k);

      for(int si=0; si<sampleIdx.Count; si++){
        int p = sampleIdx[si];
        int x = p % w;
        int y = p / w;
        int off = y*stride + x*4;
        double r = pixels[off + 2];
        double g = pixels[off + 1];
        double b = pixels[off + 0];
        double a = pixels[off + 3];

        int best = 0;
        double bestDist = double.PositiveInfinity;
        for(int i=0;i<k;i++){
          double dr = r - cr[i];
          double dg = g - cg[i];
          double db = b - cb[i];
          double da = a - ca[i];
          double dist = dr*dr + dg*dg + db*db + da*da;
          if(dist < bestDist){
            bestDist = dist;
            best = i;
          }
        }
        counts[best]++;
        sr[best] += r;
        sg[best] += g;
        sb[best] += b;
        sa[best] += a;
      }

      for(int i=0;i<k;i++){
        if(counts[i] == 0){
          // Re-init empty cluster
          int p = sampleIdx[rnd.Next(sampleIdx.Count)];
          int x = p % w;
          int y = p / w;
          int off = y*stride + x*4;
          cb[i] = pixels[off + 0];
          cg[i] = pixels[off + 1];
          cr[i] = pixels[off + 2];
          ca[i] = pixels[off + 3];
        }else{
          cr[i] = sr[i]/counts[i];
          cg[i] = sg[i]/counts[i];
          cb[i] = sb[i]/counts[i];
          ca[i] = sa[i]/counts[i];
        }
      }
    }

    // Build palette and mapped index per pixel
    Bitmap dst = new Bitmap(w, h, PixelFormat.Format8bppIndexed);

    // Lock destination for writing indices
    BitmapData dstData = dst.LockBits(rect, ImageLockMode.WriteOnly, PixelFormat.Format8bppIndexed);
    int dstStride = dstData.Stride;
    byte[] idxBytes = new byte[dstStride * h];

    // Create palette and set after mapping
    Color[] colors = new Color[k];
    for(int i=0;i<k;i++){
      int r = (int)Math.Round(cr[i]); if(r<0) r=0; if(r>255) r=255;
      int g = (int)Math.Round(cg[i]); if(g<0) g=0; if(g>255) g=255;
      int b = (int)Math.Round(cb[i]); if(b<0) b=0; if(b>255) b=255;
      int a = (int)Math.Round(ca[i]); if(a<0) a=0; if(a>255) a=255;
      colors[i] = Color.FromArgb(a, r, g, b);
    }

    // Fill indices
    for(int y=0;y<h;y++){
      for(int x=0;x<w;x++){
        int p = y*w + x;
        int off = y*stride + x*4;
        double r = pixels[off + 2];
        double g = pixels[off + 1];
        double b = pixels[off + 0];
        double a = pixels[off + 3];

        int best = 0;
        double bestDist = double.PositiveInfinity;
        for(int i=0;i<k;i++){
          double dr = r - cr[i];
          double dg = g - cg[i];
          double db = b - cb[i];
          double da = a - ca[i];
          double dist = dr*dr + dg*dg + db*db + da*da;
          if(dist < bestDist){
            bestDist = dist;
            best = i;
          }
        }
        idxBytes[y*dstStride + x] = (byte)best;
      }
    }

    System.Runtime.InteropServices.Marshal.Copy(idxBytes, 0, dstData.Scan0, idxBytes.Length);
    dst.UnlockBits(dstData);

    // Set palette
    ColorPalette palette = dst.Palette;
    for(int i=0;i<256;i++){
      if(i < k) palette.Entries[i] = colors[i];
      else palette.Entries[i] = Color.FromArgb(255,0,0,0);
    }
    dst.Palette = palette;

    return dst;
  }
}
"@

  if(-not ([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.FullName -like '*PngQuantizer*' })){
    Add-Type -TypeDefinition $cs -Language CSharp -ReferencedAssemblies @('System.Drawing') -ErrorAction Stop | Out-Null
  }

  # 候选色数：越少越小，但画质下降
  $kCandidates = @(256, 240, 224, 192, 200, 208, 176, 160, 144, 128, 96, 80, 64, 48, 32)
  $bestDiff = [double]::PositiveInfinity
  $bestK = $null
  $bestSizeBytes = 0
  $tempOut = $outPath

  $pngCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq 'image/png' } |
    Select-Object -First 1

  if(-not $pngCodec){
    throw 'PNG encoder not found'
  }

  foreach($k in $kCandidates){
    # sampleStep 越大越快，效果稍差；先用 2
    $candidate = $null
    try{
      $candidate = [PngQuantizer]::QuantizeTo8bppIndexed($bmp, $k, 2, 8, (1234 + $k))

      if(Test-Path -LiteralPath $tempOut){ Remove-Item -LiteralPath $tempOut -Force }

      # PNG compression: System.Drawing may not honor fully, but keep it high anyway
      try {
        $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
        $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
          [System.Drawing.Imaging.Encoder]::Compression,
          9L
        )
        $candidate.Save($tempOut, $pngCodec, $encParams)
      } catch {
        $candidate.Save($tempOut, $pngCodec, $null)
      }

      $sizeBytes = (Get-Item -LiteralPath $tempOut).Length
      $diff = [Math]::Abs($sizeBytes - $MaxPngSizeBytes)
      Write-Output ("k={0} size_bytes={1}" -f $k, $sizeBytes)

      if($diff -lt $bestDiff){
        $bestDiff = $diff
        $bestK = $k
        $bestSizeBytes = $sizeBytes
      }
    } finally {
      if($candidate -ne $null){
        $candidate.Dispose()
      }
    }
  }

  # 重新生成一次最佳 k，再在不同 PNG compression 级别里选最接近目标大小的
  if(Test-Path -LiteralPath $outPath){ Remove-Item -LiteralPath $outPath -Force }
  $finalBmp = [PngQuantizer]::QuantizeTo8bppIndexed($bmp, $bestK, 2, 8, (5678 + $bestK))
  $tmpOut = [System.IO.Path]::Combine(
    $DownloadsDir,
    ([System.IO.Path]::GetFileNameWithoutExtension($outPath) + '_tmp.png')
  )
  if(Test-Path -LiteralPath $tmpOut){ Remove-Item -LiteralPath $tmpOut -Force }

  $compressionLevels = @(9, 7, 6, 5, 4, 3, 2, 1, 0)
  $bestComp = $null
  $bestSizeBytes = 0
  $bestDiffFinal = [double]::PositiveInfinity

  try{
    foreach($comp in $compressionLevels){
      if(Test-Path -LiteralPath $tmpOut){ Remove-Item -LiteralPath $tmpOut -Force }

      try {
        $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
        $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
          [System.Drawing.Imaging.Encoder]::Compression,
          [long]$comp
        )
        $finalBmp.Save($tmpOut, $pngCodec, $encParams)
      } catch {
        $finalBmp.Save($tmpOut, $pngCodec, $null)
      }

      $sizeBytes = (Get-Item -LiteralPath $tmpOut).Length
      $diff = [Math]::Abs($sizeBytes - $MaxPngSizeBytes)
      Write-Output ("k={0} comp={1} size_bytes={2}" -f $bestK, $comp, $sizeBytes)

      if($diff -lt $bestDiffFinal){
        $bestDiffFinal = $diff
        $bestComp = $comp
        $bestSizeBytes = $sizeBytes
      }
    }

    if(Test-Path -LiteralPath $outPath){ Remove-Item -LiteralPath $outPath -Force }
    if(Test-Path -LiteralPath $tmpOut){ Remove-Item -LiteralPath $tmpOut -Force }

    # 用最佳 compression 再保存一次到最终路径
    $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
    $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
      [System.Drawing.Imaging.Encoder]::Compression,
      [long]$bestComp
    )
    $finalBmp.Save($outPath, $pngCodec, $encParams)
  } finally {
    $finalBmp.Dispose()
    if(Test-Path -LiteralPath $tmpOut){ Remove-Item -LiteralPath $tmpOut -Force }
  }

  Write-Output ("OUTPUT={0}" -f $outPath)
  Write-Output ("FINAL_K={0}" -f $bestK)
  Write-Output ("FINAL_COMP={0}" -f $bestComp)
  Write-Output ("FINAL_SIZE_BYTES={0}" -f $bestSizeBytes)
  Write-Output ("FINAL_SIZE_KB={0}" -f [Math]::Round($bestSizeBytes/1KB, 2))
}
finally {
  if($bmp -ne $null){ $bmp.Dispose() }
}

