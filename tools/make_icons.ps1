# Рисует иконки Nika для Briefcase: square, round и adaptive.
# Пчела на иконке — это дефолт BeeWare: Briefcase не нашёл resources/icon-*.png.
# Запуск: powershell -ExecutionPolicy Bypass -File tools/make_icons.ps1

Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $root 'resources'
New-Item -ItemType Directory -Force $out | Out-Null

$accent = [System.Drawing.Color]::FromArgb(200, 30, 58)
$bg     = [System.Drawing.Color]::FromArgb(13, 13, 15)

function New-RoundPath([double]$x, [double]$y, [double]$w, [double]$h, [double]$r) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = [Math]::Min($r * 2, [Math]::Min($w, $h))
    if ($d -le 0) { $p.AddRectangle((New-Object System.Drawing.RectangleF([single]$x, [single]$y, [single]$w, [single]$h))); return $p }
    $p.AddArc([single]$x, [single]$y, [single]$d, [single]$d, 180, 90)
    $p.AddArc([single]($x + $w - $d), [single]$y, [single]$d, [single]$d, 270, 90)
    $p.AddArc([single]($x + $w - $d), [single]($y + $h - $d), [single]$d, [single]$d, 0, 90)
    $p.AddArc([single]$x, [single]($y + $h - $d), [single]$d, [single]$d, 90, 90)
    $p.CloseFigure()
    return $p
}

function New-NikaIcon([int]$size, [string]$mode) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.TextRenderingHint = 'AntiAliasGridFit'
    $g.Clear([System.Drawing.Color]::Transparent)

    $inset = [Math]::Max(1.0, $size * 0.022)
    $radius = $size * 0.19

    if ($mode -eq 'square') {
        $path = New-RoundPath $inset $inset ($size - 2 * $inset) ($size - 2 * $inset) $radius
        $fill = New-Object System.Drawing.SolidBrush($bg)
        $g.FillPath($fill, $path)
        $fill.Dispose()
        $pen = New-Object System.Drawing.Pen($accent, [single][Math]::Max(1.5, $size * 0.018))
        $g.DrawPath($pen, $path)
        $pen.Dispose(); $path.Dispose()
    }
    elseif ($mode -eq 'round') {
        $fill = New-Object System.Drawing.SolidBrush($bg)
        $g.FillEllipse($fill, [single]$inset, [single]$inset,
                       [single]($size - 2 * $inset), [single]($size - 2 * $inset))
        $fill.Dispose()
        $pen = New-Object System.Drawing.Pen($accent, [single][Math]::Max(1.5, $size * 0.018))
        $g.DrawEllipse($pen, [single]$inset, [single]$inset,
                       [single]($size - 2 * $inset), [single]($size - 2 * $inset))
        $pen.Dispose()
    }

    $glyphScale = 0.34
    if ($mode -eq 'adaptive') { $glyphScale = 0.46 }

    $font = New-Object System.Drawing.Font('Segoe UI', [single]($size * $glyphScale),
                                           [System.Drawing.FontStyle]::Bold,
                                           [System.Drawing.GraphicsUnit]::Pixel)
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = 'Center'
    $fmt.LineAlignment = 'Center'
    $brush = New-Object System.Drawing.SolidBrush($accent)
    $shift = 0.0
    if ($mode -eq 'adaptive') { $shift = -0.05 * $size }
    $rect = New-Object System.Drawing.RectangleF([single]$shift, 0,
                                                 [single]$size, [single]$size)
    $g.DrawString('N', $font, $brush, $rect, $fmt)

    $r = $size * 0.075
    $dotX = $size * 0.63 + $shift
    $dotY = $size * 0.70
    $g.FillEllipse($brush, [single]$dotX, [single]$dotY,
                   [single]($r * 2), [single]($r * 2))

    $brush.Dispose(); $fmt.Dispose(); $font.Dispose(); $g.Dispose()
    return $bmp
}

foreach ($s in @(48, 72, 96, 144, 192, 320, 480, 640, 960, 1280)) {
    $img = New-NikaIcon $s 'square'
    $img.Save((Join-Path $out "icon-square-$s.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $img.Dispose()
}
foreach ($s in @(48, 72, 96, 144, 192)) {
    $img = New-NikaIcon $s 'round'
    $img.Save((Join-Path $out "icon-round-$s.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $img.Dispose()
}
foreach ($s in @(108, 162, 216, 324, 432)) {
    $img = New-NikaIcon $s 'adaptive'
    $img.Save((Join-Path $out "icon-adaptive-$s.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $img.Dispose()
}

Write-Output "готово: resources/icon-*.png"
