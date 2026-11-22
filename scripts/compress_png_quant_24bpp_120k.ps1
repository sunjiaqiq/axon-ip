param(
  [string]$DownloadsDir = 'D:\Documents\Downloads',
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

  $cs = @"
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;

public static class PngQuantizer24
{
  public static Bitmap QuantizeTo24bpp(Bitmap src, int k, int sampleStep, int iterations, int seed)
  {
    int w = src.Width;
    int h = src.Height;

    Bitmap src32 = new Bitmap(w, h, PixelFormat.Format32bppArgb);
    using (var g = Graphics.FromImage(src32))
      g.DrawImage(src, new Rectangle(0,0,w,h), new Rectangle(0,0,w,h), GraphicsUnit.Pixel);

    var rect = new Rectangle(0,0,w,h);
    BitmapData data = src32.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
    int stride = data.Stride;

    byte[] pixels = new byte[stride * h];
    System.Runtime.InteropServices.Marshal.Copy(data.Scan0, pixels, 0, pixels.Length);
    src32.UnlockBits(data);

    List<int> sampleIdx = new List<int>();
    for(int y=0; y<h; y+=sampleStep){
      for(int x=0; x<w; x+=sampleStep){
        sampleIdx.Add(y*w + x);
      }
    }
    if(sampleIdx.Count == 0) sampleIdx.Add(0);

    Random rnd = new Random(seed);
    double[] cr = new double[k];
    double[] cg = new double[k];
    double[] cb = new double[k];
    double[] ca = new double[k];

    for(int i=0;i<k;i++){
      int p = sampleIdx[rnd.Next(sampleIdx.Count)];
      int x = p % w;
      int y = p / w;
      int off = y*stride + x*4;
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

    Bitmap dst = new Bitmap(w, h, PixelFormat.Format32bppArgb);
    BitmapData dstData = dst.LockBits(rect, ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
    int dstStride = dstData.Stride;
    byte[] outBytes = new byte[dstStride * h];

    for(int y=0;y<h;y++){
      for(int x=0;x<w;x++){
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

        int o = y*dstStride + x*4;
        outBytes[o + 0] = (byte)Math.Max(0, Math.Min(255, Math.Round(cb[best])));
        outBytes[o + 1] = (byte)Math.Max(0, Math.Min(255, Math.Round(cg[best])));
        outBytes[o + 2] = (byte)Math.Max(0, Math.Min(255, Math.Round(cr[best])));
        outBytes[o + 3] = (byte)Math.Max(0, Math.Min(255, Math.Round(ca[best])));
      }
    }

    System.Runtime.InteropServices.Marshal.Copy(outBytes, 0, dstData.Scan0, outBytes.Length);
    dst.UnlockBits(dstData);

    return dst;
  }
}
"@

  if(-not ([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.FullName -like '*PngQuantizer24*' })){
    Add-Type -TypeDefinition $cs -Language CSharp -ReferencedAssemblies @('System.Drawing') -ErrorAction Stop | Out-Null
  }

  $pngCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq 'image/png' } |
    Select-Object -First 1
  if(-not $pngCodec){ throw 'PNG encoder not found' }

  $compression = 9L
  $compressionLevels = @($compression)
  $kCandidates = @(256, 240, 224, 200, 192, 176, 160, 152, 144, 136, 128, 120, 112, 104, 96, 88, 80, 72, 64)

  $bestDiff = [double]::PositiveInfinity
  $bestK = $null
  $bestSizeBytes = 0

  $tmpOut = [System.IO.Path]::Combine($DownloadsDir, (([System.IO.Path]::GetFileNameWithoutExtension($outPath)) + '_tmp.png'))
  if(Test-Path -LiteralPath $tmpOut){ Remove-Item -LiteralPath $tmpOut -Force }

  foreach($k in $kCandidates){
    $candidate = $null
    try {
      $candidate = [PngQuantizer24]::QuantizeTo24bpp($bmp, $k, 2, 8, (9999 + $k))
      if(Test-Path -LiteralPath $tmpOut){ Remove-Item -LiteralPath $tmpOut -Force }

      try{
        $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
        $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
          [System.Drawing.Imaging.Encoder]::Compression,
          $compression
        )
        $candidate.Save($tmpOut, $pngCodec, $encParams)
      } catch {
        $candidate.Save($tmpOut, $pngCodec, $null)
      }

      $sizeBytes = (Get-Item -LiteralPath $tmpOut).Length
      $diff = [Math]::Abs($sizeBytes - $MaxPngSizeBytes)
      Write-Output ("k={0} size_bytes={1}" -f $k, $sizeBytes)

      if($diff -lt $bestDiff){
        $bestDiff = $diff
        $bestK = $k
        $bestSizeBytes = $sizeBytes
      }
    } finally {
      if($candidate -ne $null){ $candidate.Dispose() }
    }
  }

  if(Test-Path -LiteralPath $outPath){ Remove-Item -LiteralPath $outPath -Force }
  if(Test-Path -LiteralPath $tmpOut){ Remove-Item -LiteralPath $tmpOut -Force }

  $finalBmp = [PngQuantizer24]::QuantizeTo24bpp($bmp, $bestK, 2, 8, (8888 + $bestK))
  try{
    $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
    $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
      [System.Drawing.Imaging.Encoder]::Compression,
      $compression
    )
    $finalBmp.Save($outPath, $pngCodec, $encParams)
  } finally {
    $finalBmp.Dispose()
  }

  $bestSizeBytes = (Get-Item -LiteralPath $outPath).Length
  Write-Output ("OUTPUT={0}" -f $outPath)
  Write-Output ("FINAL_K={0}" -f $bestK)
  Write-Output ("FINAL_SIZE_BYTES={0}" -f $bestSizeBytes)
  Write-Output ("FINAL_SIZE_KB={0}" -f [Math]::Round($bestSizeBytes/1KB, 2))
}
finally {
  if($bmp -ne $null){ $bmp.Dispose() }
}

