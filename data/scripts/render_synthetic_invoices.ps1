param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)

Add-Type -AssemblyName System.Drawing
$rows = (Get-Content -Raw -Encoding UTF8 $Manifest | ConvertFrom-Json).records
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$width = 1240
$height = 1754
$rtl = New-Object System.Drawing.StringFormat
$rtl.FormatFlags = [System.Drawing.StringFormatFlags]::DirectionRightToLeft
$ltr = New-Object System.Drawing.StringFormat
$brush = [System.Drawing.Brushes]::Black
$ink = [System.Drawing.Color]::FromArgb(20,34,53)
$muted = [System.Drawing.Color]::FromArgb(96,113,127)
$line = [System.Drawing.Color]::FromArgb(217,226,232)
$accents = @(
    [System.Drawing.Color]::FromArgb(12,101,114),
    [System.Drawing.Color]::FromArgb(180,88,38),
    [System.Drawing.Color]::FromArgb(39,75,132),
    [System.Drawing.Color]::FromArgb(106,72,132),
    [System.Drawing.Color]::FromArgb(43,116,78)
)
$pales = @(
    [System.Drawing.Color]::FromArgb(240,247,247),
    [System.Drawing.Color]::FromArgb(250,243,237),
    [System.Drawing.Color]::FromArgb(239,243,250),
    [System.Drawing.Color]::FromArgb(246,241,250),
    [System.Drawing.Color]::FromArgb(240,247,242)
)
$fontBrand = New-Object System.Drawing.Font('Arial',20,[System.Drawing.FontStyle]::Bold)
$fontTitle = New-Object System.Drawing.Font('Arial',34,[System.Drawing.FontStyle]::Bold)
$fontVendor = New-Object System.Drawing.Font('Arial',27,[System.Drawing.FontStyle]::Bold)
$fontLabel = New-Object System.Drawing.Font('Arial',16)
$fontValue = New-Object System.Drawing.Font('Arial',20,[System.Drawing.FontStyle]::Bold)
$fontTable = New-Object System.Drawing.Font('Arial',18)
$fontNote = New-Object System.Drawing.Font('Arial',12)

foreach ($r in $rows) {
    $variant = [int]$r.layout_variant
    $accent = $accents[$variant]
    $pale = $pales[$variant]
    $bmp = New-Object System.Drawing.Bitmap $width,$height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $paper = if ($variant -eq 3) { [System.Drawing.Color]::FromArgb(252,250,253) } else { [System.Drawing.Color]::White }
    $g.Clear($paper)
    switch ($variant) {
        0 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,18) }
        1 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,22,$height) }
        2 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,145) }
        3 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,12); $g.FillRectangle((New-Object System.Drawing.SolidBrush $pale),0,12,$width,155) }
        4 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),950,0,290,24); $g.FillRectangle((New-Object System.Drawing.SolidBrush $pale),65,68,1110,70) }
    }
    $isAr = $r.language -eq 'ar'
    $fmt = if ($isAr) { $rtl } else { $ltr }
    $x = if ($isAr) { 1170 } else { 70 }
    $brandBrush = if ($variant -eq 2) { [System.Drawing.Brushes]::White } else { New-Object System.Drawing.SolidBrush $accent }
    $brandY = if ($variant -eq 2) { 54 } else { 70 }
    $brandX = if ($variant -eq 4) { 90 } else { 70 }
    $g.DrawString('SECUREFIN | TEST FIXTURE',$fontBrand,$brandBrush,$brandX,$brandY,$ltr)
    $title = if ($isAr) { 'فاتورة ضريبية تجريبية' } else { 'Synthetic Tax Invoice' }
    $titleY = if ($variant -eq 3) { 170 } elseif ($variant -eq 2) { 175 } else { 145 }
    $titleBrush = New-Object System.Drawing.SolidBrush $ink
    $g.DrawString($title,$fontTitle,$titleBrush,$x,$titleY,$fmt)
    $vendor = if ($isAr) { $r.vendor_name_ar } elseif ($r.language -eq 'en') { $r.vendor_name_en } else { "$($r.vendor_name_ar) / $($r.vendor_name_en)" }
    $vendorY = if ($variant -eq 3) { 260 } else { 235 }
    $vendorInk = $ink
    if ($variant -eq 2) {
        $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),65,$vendorY,1110,100)
        $vendorInk = [System.Drawing.Color]::White
    } elseif ($variant -eq 3) {
        $g.DrawLine((New-Object System.Drawing.Pen $accent,4),65,$vendorY+90,1175,$vendorY+90)
    } else {
        $g.FillRectangle((New-Object System.Drawing.SolidBrush $pale),65,$vendorY,1110,92)
        $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),65,$vendorY,7,92)
    }
    $vendorBrush = New-Object System.Drawing.SolidBrush $vendorInk
    $g.DrawString($vendor,$fontVendor,$vendorBrush,$x,$vendorY+27,$fmt)

    $labels = if ($isAr) { @('رقم الفاتورة','التاريخ','الرقم الضريبي','حساب المورد التجريبي') } else { @('Invoice No.','Date','Tax ID','Synthetic vendor account') }
    $values = @($r.invoice_number,$r.invoice_date,$r.tax_id,$r.invoice_iban)
    $metaTop = if ($variant -eq 2) { 385 } elseif ($variant -eq 3) { 380 } else { 370 }
    if ($variant -eq 3) {
        $positions = @(
            [pscustomobject]@{ X=70; Y=$metaTop },
            [pscustomobject]@{ X=70; Y=($metaTop+110) },
            [pscustomobject]@{ X=70; Y=($metaTop+220) },
            [pscustomobject]@{ X=70; Y=($metaTop+330) }
        )
    } elseif ($variant -eq 4) {
        $positions = @(
            [pscustomobject]@{ X=650; Y=$metaTop }, [pscustomobject]@{ X=70; Y=$metaTop },
            [pscustomobject]@{ X=650; Y=($metaTop+135) }, [pscustomobject]@{ X=70; Y=($metaTop+135) }
        )
    } else {
        $offset = if ($variant -eq 1) { 20 } elseif ($variant -eq 2) { 15 } else { 0 }
        $positions = @(
            [pscustomobject]@{ X=70; Y=($metaTop+$offset) }, [pscustomobject]@{ X=650; Y=($metaTop+$offset) },
            [pscustomobject]@{ X=70; Y=($metaTop+135+$offset) }, [pscustomobject]@{ X=650; Y=($metaTop+135+$offset) }
        )
    }
    for ($i=0; $i -lt 4; $i++) {
        $px=[int]$positions[$i].X; $py=[int]$positions[$i].Y
        $boxWidth = if ($variant -eq 3) { 1100 } else { 520 }
        if ($variant -ne 3) { $g.DrawRectangle((New-Object System.Drawing.Pen $line,2),$px,$py,$boxWidth,105) }
        $tx = if ($isAr) { $px+$boxWidth-25 } else { $px+18 }
        $valueX = if ($variant -eq 3 -and $isAr) { $px+400 } elseif ($variant -eq 3) { $px+700 } else { $tx }
        $g.DrawString($labels[$i],$fontLabel,(New-Object System.Drawing.SolidBrush $muted),$tx,$py+14,$fmt)
        $g.DrawString([string]$values[$i],$fontValue,$brush,$valueX,$py+53,$fmt)
    }

    $tableTitle = if ($isAr) { @('الوصف','الكمية','السعر') } else { @('Description','Qty','Unit price') }
    $item = if ($isAr) { @('أدوات مكتبية','خدمات صيانة','أجهزة شبكات','مواد تعبئة','خدمات نقل')[[int]$r.vendor_index % 5] } else { @('Office supplies','Maintenance service','Network equipment','Packaging material','Transport service')[[int]$r.vendor_index % 5] }
    $tableY = if ($variant -eq 3) { 850 } elseif ($variant -eq 2) { 725 } else { 680 }
    $tableInk = if ($variant -eq 4) { $accent } else { $ink }
    $g.FillRectangle((New-Object System.Drawing.SolidBrush $tableInk),70,$tableY,1100,58)
    if ($isAr) {
        $g.DrawString($tableTitle[0],$fontTable,[System.Drawing.Brushes]::White,1140,$tableY+16,$rtl)
        $g.DrawString($tableTitle[1],$fontTable,[System.Drawing.Brushes]::White,600,$tableY+16,$rtl)
        $g.DrawString($tableTitle[2],$fontTable,[System.Drawing.Brushes]::White,250,$tableY+16,$rtl)
    } else {
        $g.DrawString($tableTitle[0],$fontTable,[System.Drawing.Brushes]::White,90,$tableY+16,$ltr)
        $g.DrawString($tableTitle[1],$fontTable,[System.Drawing.Brushes]::White,650,$tableY+16,$ltr)
        $g.DrawString($tableTitle[2],$fontTable,[System.Drawing.Brushes]::White,900,$tableY+16,$ltr)
    }
    $subtotal = [int]$r.subtotal_egp
    $tax = [double]$r.tax_egp
    $total = [double]$r.total_egp
    if ($isAr) {
        $g.DrawString($item,$fontTable,$brush,1140,$tableY+95,$rtl)
        $g.DrawString('1',$fontTable,$brush,600,$tableY+95,$ltr)
        $g.DrawString(("{0:N2} EGP" -f $subtotal),$fontTable,$brush,250,$tableY+95,$ltr)
    } else {
        $g.DrawString($item,$fontTable,$brush,90,$tableY+95,$ltr)
        $g.DrawString('1',$fontTable,$brush,650,$tableY+95,$ltr)
        $g.DrawString(("{0:N2} EGP" -f $subtotal),$fontTable,$brush,900,$tableY+95,$ltr)
    }
    $totals = if ($isAr) { @(@('الإجمالي قبل الضريبة',("{0:N2} ج.م" -f $subtotal)),@('ضريبة القيمة المضافة (14%)',("{0:N2} ج.م" -f $tax)),@('الإجمالي المستحق',("{0:N2} ج.م" -f $total))) } else { @(@('Subtotal',("{0:N2} EGP" -f $subtotal)),@('VAT (14%)',("{0:N2} EGP" -f $tax)),@('Total due',("{0:N2} EGP" -f $total))) }
    $y=if ($variant -eq 3) { 1090 } elseif ($variant -eq 2) { 1010 } else { 930 }
    foreach ($pair in $totals) {
        $g.DrawString($pair[0],$fontTable,$brush,$(if ($isAr) { 830 } else { 720 }),$y,$fmt)
        $g.DrawString($pair[1],$fontTable,$brush,$(if ($isAr) { 1145 } else { 930 }),$y,$(if ($isAr) { $rtl } else { $ltr }))
        $y += 58
    }
    $g.DrawLine((New-Object System.Drawing.Pen $line,2),70,1600,1170,1600)
    $g.DrawString("Synthetic test data - not valid for payment or tax filing - $($r.id) / 50",$fontNote,(New-Object System.Drawing.SolidBrush $muted),$width/2,1630,[System.Drawing.StringFormat]::GenericDefault)
    $png = Join-Path $OutputDirectory (([System.IO.Path]::GetFileNameWithoutExtension($r.file)) + '.png')
    $bmp.Save($png,[System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
}
$rtl.Dispose(); $ltr.Dispose()
Write-Output "Rendered $($rows.Count) invoice images to $OutputDirectory"
