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
$bestQ = $null
$bestSizeBytes = 0
$bestDiff = [double]::PositiveInfinity

try {
  # For System.Drawing on Windows
  try {
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop | Out-Null
  } catch {
    Add-Type -AssemblyName System.Drawing.Common -ErrorAction Stop | Out-Null
  }

  $bmp = [System.Drawing.Bitmap]::FromFile($inPath)

  $pngCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq 'image/png' } |
    Select-Object -First 1

  if(-not $pngCodec){
    throw 'PNG encoder not found'
  }

  # PNG encoder "Compression" usually maps to zlib compression level (0..9).
  $compressionLevels = @(9,8,7,6,5,4,3,2,1,0)

  foreach($level in $compressionLevels){
    if(Test-Path -LiteralPath $outPath){ Remove-Item -LiteralPath $outPath -Force }

    try {
      $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
      $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
        [System.Drawing.Imaging.Encoder]::Compression,
        [long]$level
      )
      $bmp.Save($outPath, $pngCodec, $encParams)
    } catch {
      # If compression parameter isn't supported, fall back to default PNG save.
      $bmp.Save($outPath, $pngCodec, $null)
    }

    $sizeBytes = (Get-Item -LiteralPath $outPath).Length
    $diff = [Math]::Abs($sizeBytes - $MaxPngSizeBytes)
    Write-Output ("level={0} size_bytes={1}" -f $level, $sizeBytes)
    if($diff -lt $bestDiff){
      $bestDiff = $diff
      $bestQ = $level
      $bestSizeBytes = $sizeBytes
    }
  }

  # Re-save with best level to guarantee final file matches
  if(Test-Path -LiteralPath $outPath){ Remove-Item -LiteralPath $outPath -Force }
  $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
  $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
    [System.Drawing.Imaging.Encoder]::Compression,
    [long]$bestQ
  )
  $bmp.Save($outPath, $pngCodec, $encParams)
  $bestSizeBytes = (Get-Item -LiteralPath $outPath).Length

  Write-Output ("OUTPUT={0}" -f $outPath)
  Write-Output ("FINAL_COMPRESSION_LEVEL={0}" -f $bestQ)
  Write-Output ("FINAL_SIZE_BYTES={0}" -f $bestSizeBytes)
  Write-Output ("FINAL_SIZE_KB={0}" -f [Math]::Round($bestSizeBytes/1KB,2))
} finally {
  if($bmp -ne $null){
    $bmp.Dispose()
  }
}

