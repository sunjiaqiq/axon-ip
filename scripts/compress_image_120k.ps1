param(
  [string]$DownloadsDir = 'D:\Documents\Downloads',
  [long]$TargetPngSizeBytes = 395201,
  [long]$MaxJpegSizeBytes = 120000
)

$null = $null
try {
  Add-Type -AssemblyName System.Drawing -ErrorAction Stop | Out-Null
} catch {
  try {
    Add-Type -AssemblyName System.Drawing.Common -ErrorAction Stop | Out-Null
  } catch {
    throw "System.Drawing types not available in this PowerShell runtime. Error: $($_.Exception.Message)"
  }
}

$png = Get-ChildItem -LiteralPath $DownloadsDir -Filter '*.png' |
  Where-Object {
    $_.Length -eq $TargetPngSizeBytes -and $_.Name -like '* (1).png'
  } |
  Select-Object -First 1

if(-not $png){
  throw "Target PNG not found. dir='$DownloadsDir' sizeBytes=$TargetPngSizeBytes"
}

$inPath = $png.FullName
$outPath = Join-Path $DownloadsDir (([System.IO.Path]::GetFileNameWithoutExtension($inPath)) + '_120k.jpg')

if(Test-Path -LiteralPath $outPath){
  Remove-Item -LiteralPath $outPath -Force
}

$bmp = [System.Drawing.Bitmap]::FromFile($inPath)
try {
  $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq 'image/jpeg' } |
    Select-Object -First 1

  if(-not $codec){
    throw 'JPEG encoder not found'
  }

  # 目标是尽量贴近 120KB，而不是一旦 <=120KB 就停
  $qualityCandidates = @(100,99,98,97,96,95,94,93,92,91,90,85,80,75,70,65,60,55,50,45,40,35,30,25,20,15,10)
  $bestQ = $null
  $bestSizeBytes = 0
  $bestDiff = [double]::PositiveInfinity

  foreach($q in $qualityCandidates){
    if(Test-Path -LiteralPath $outPath){
      Remove-Item -LiteralPath $outPath -Force
    }

    $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
    $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
      [System.Drawing.Imaging.Encoder]::Quality,
      [long]$q
    )

    $bmp.Save($outPath, $codec, $encParams)
    $sizeBytes = (Get-Item -LiteralPath $outPath).Length

    Write-Output ("q={0} size_bytes={1}" -f $q, $sizeBytes)

    $diff = [Math]::Abs($sizeBytes - $MaxJpegSizeBytes)
    if($diff -lt $bestDiff){
      $bestDiff = $diff
      $bestQ = $q
      $bestSizeBytes = $sizeBytes
    }
  }

  # 用最优质量再生成一次，确保 outPath 与 bestQ 一致
  if(Test-Path -LiteralPath $outPath){
    Remove-Item -LiteralPath $outPath -Force
  }
  $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
  $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
    [System.Drawing.Imaging.Encoder]::Quality,
    [long]$bestQ
  )
  $bmp.Save($outPath, $codec, $encParams)
  $bestSizeBytes = (Get-Item -LiteralPath $outPath).Length

  Write-Output ("OUTPUT={0}" -f $outPath)
  Write-Output ("FINAL_Q={0}" -f $bestQ)
  Write-Output ("FINAL_SIZE_KB={0}" -f [Math]::Round($bestSizeBytes/1KB, 2))
}
finally {
  $bmp.Dispose()
}

