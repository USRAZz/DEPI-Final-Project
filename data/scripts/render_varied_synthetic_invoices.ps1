param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)

Add-Type -AssemblyName System.Drawing
$rows = (Get-Content -Raw -Encoding UTF8 $Manifest | ConvertFrom-Json).records
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$width = 1240; $height = 1754
$rtl = New-Object System.Drawing.StringFormat
$rtl.FormatFlags = [System.Drawing.StringFormatFlags]::DirectionRightToLeft
$ltr = New-Object System.Drawing.StringFormat
$accents = @(
    [System.Drawing.Color]::FromArgb(28,91,119), [System.Drawing.Color]::FromArgb(139,73,48),
    [System.Drawing.Color]::FromArgb(48,78,132), [System.Drawing.Color]::FromArgb(69,111,79),
    [System.Drawing.Color]::FromArgb(104,76,126), [System.Drawing.Color]::FromArgb(36,110,110),
    [System.Drawing.Color]::FromArgb(125,86,40), [System.Drawing.Color]::FromArgb(50,92,103),
    [System.Drawing.Color]::FromArgb(116,61,72), [System.Drawing.Color]::FromArgb(65,83,125)
)
$muted = [System.Drawing.Color]::FromArgb(92,101,109)
$line = [System.Drawing.Color]::FromArgb(190,194,198)
$ink = [System.Drawing.Color]::FromArgb(24,32,39)
$blackBrush = [System.Drawing.Brushes]::Black
$fontBrand = New-Object System.Drawing.Font('Arial',17,[System.Drawing.FontStyle]::Bold)
$fontTitle = New-Object System.Drawing.Font('Arial',27,[System.Drawing.FontStyle]::Bold)
$fontVendor = New-Object System.Drawing.Font('Arial',23,[System.Drawing.FontStyle]::Bold)
$fontMeta = New-Object System.Drawing.Font('Arial',12)
$fontMetaValue = New-Object System.Drawing.Font('Arial',14,[System.Drawing.FontStyle]::Bold)
$fontNote = New-Object System.Drawing.Font('Arial',10)

foreach ($r in $rows) {
    $v = [int]$r.layout_variant
    $group = $v % 5
    $accent = $accents[$v]
    $isAr = $r.language -eq 'ar'
    $isMixed = $r.language -eq 'mixed'
    $fmt = if ($isAr) { $rtl } else { $ltr }
    $x = if ($isAr) { 1170 } else { 70 }
    $gfont = New-Object System.Drawing.Font('Arial',(18 + ($v % 3) * 2),[System.Drawing.FontStyle]::Bold)
    $cellSize = 12 + ($v % 4)
    $fontCell = New-Object System.Drawing.Font('Arial',$cellSize)
    $fontCellBold = New-Object System.Drawing.Font('Arial',$cellSize,[System.Drawing.FontStyle]::Bold)
    $bmp = New-Object System.Drawing.Bitmap $width,$height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::White)

    switch ($v) {
        0 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,22) }
        1 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,24,$height); $g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(246,246,244))),60,55,1110,92) }
        2 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,138) }
        3 { $g.DrawRectangle((New-Object System.Drawing.Pen $accent,5),48,45,1144,160) }
        4 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,12); $g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(245,245,245))),70,235,1100,95) }
        5 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,22); $g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(239,243,246))),70,55,430,100) }
        6 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),1010,0,230,24); $g.DrawLine((New-Object System.Drawing.Pen $accent,3),70,210,1170,210) }
        7 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,18,$height); $g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(242,242,242))),70,55,1100,90) }
        8 { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,0,$width,10); $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),70,235,1100,8) }
        9 { $g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(242,242,242))),0,0,$width,160); $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),0,150,$width,14) }
    }

    $brandColor = if ($v -eq 2) { [System.Drawing.Brushes]::White } else { New-Object System.Drawing.SolidBrush $accent }
    $brandY = if ($v -eq 2) { 42 } elseif ($v -eq 3) { 58 } else { 70 }
    $g.DrawString('SECUREFIN | TEST INVOICE',$fontBrand,$brandColor,75,$brandY,$ltr)
    $title = if ($isAr) { 'فاتورة ضريبية' } elseif ($isMixed) { 'فاتورة ضريبية | TAX INVOICE' } else { 'TAX INVOICE' }
    $titleY = if ($v -eq 3) { 94 } elseif ($v -eq 2) { 172 } else { 165 }
    $titleBrush = New-Object System.Drawing.SolidBrush $ink
    $g.DrawString($title,$fontTitle,$titleBrush,$x,$titleY,$fmt)

    $vendor = if ($isAr) { [string]$r.vendor_name_ar } elseif ($r.language -eq 'en') { [string]$r.vendor_name_en } else { "$($r.vendor_name_ar) / $($r.vendor_name_en)" }
    $vendorY = if ($v -eq 2) { 225 } else { 270 }
    $vendorBrush = if ($v -eq 2) { [System.Drawing.Brushes]::White } else { New-Object System.Drawing.SolidBrush $ink }
    if ($v -eq 2) { $g.FillRectangle((New-Object System.Drawing.SolidBrush $accent),65,$vendorY,1110,82) }
    elseif ($v -eq 4) { $g.DrawRectangle((New-Object System.Drawing.Pen $line,2),65,$vendorY,1110,90) }
    else { $g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(248,248,247))),65,$vendorY,1110,90) }
    $g.DrawString($vendor,$fontVendor,$vendorBrush,$x,$vendorY+24,$fmt)

    $labels = if ($isAr) { @('رقم الفاتورة','التاريخ','أمر الشراء','الرقم الضريبي','حساب المورد') } elseif ($isMixed) { @('رقم الفاتورة / Invoice No.','التاريخ / Date','أمر الشراء / PO','الرقم الضريبي / Tax ID','حساب المورد / Account') } else { @('Invoice No.','Invoice date','Purchase order','Tax registration no.','Vendor account') }
    $values = @($r.invoice_number,$r.invoice_date,$r.purchase_order,$r.tax_id,$r.invoice_iban)
    $metaStart = if ($v -eq 2) { 350 } else { 390 }
    if ($group -eq 0) {
        $positions = @(
            [pscustomobject]@{X=70;Y=$metaStart},[pscustomobject]@{X=650;Y=$metaStart},
            [pscustomobject]@{X=70;Y=($metaStart+125)},[pscustomobject]@{X=650;Y=($metaStart+125)},
            [pscustomobject]@{X=70;Y=($metaStart+250)}
        )
    } elseif ($group -eq 1) {
        $positions = @(
            [pscustomobject]@{X=70;Y=$metaStart},[pscustomobject]@{X=70;Y=($metaStart+76)},
            [pscustomobject]@{X=70;Y=($metaStart+152)},[pscustomobject]@{X=70;Y=($metaStart+228)},
            [pscustomobject]@{X=70;Y=($metaStart+304)}
        )
    } elseif ($group -eq 2) {
        $positions = @(
            [pscustomobject]@{X=70;Y=$metaStart},[pscustomobject]@{X=430;Y=$metaStart},
            [pscustomobject]@{X=790;Y=$metaStart},[pscustomobject]@{X=70;Y=($metaStart+125)},
            [pscustomobject]@{X=650;Y=($metaStart+125)}
        )
    } elseif ($group -eq 3) {
        $positions = @(
            [pscustomobject]@{X=650;Y=$metaStart},[pscustomobject]@{X=650;Y=($metaStart+88)},
            [pscustomobject]@{X=650;Y=($metaStart+176)},[pscustomobject]@{X=70;Y=$metaStart},
            [pscustomobject]@{X=70;Y=($metaStart+88)}
        )
    } else {
        $positions = @(
            [pscustomobject]@{X=70;Y=$metaStart},[pscustomobject]@{X=650;Y=$metaStart},
            [pscustomobject]@{X=70;Y=($metaStart+150)},[pscustomobject]@{X=650;Y=($metaStart+150)},
            [pscustomobject]@{X=70;Y=($metaStart+300)}
        )
    }
    for ($j=0; $j -lt 5; $j++) {
        $px=[int]$positions[$j].X; $py=[int]$positions[$j].Y
        $wide = ($group -eq 1 -or ($group -eq 4 -and $j -eq 4))
        $boxWidth = if ($wide) { 1100 } elseif ($group -eq 2) { 350 } else { 520 }
        if (($v % 2) -eq 0) { $g.DrawRectangle((New-Object System.Drawing.Pen $line,1),$px,$py,$boxWidth,66) }
        $fieldX = if ($isAr) { $px+$boxWidth-14 } else { $px+12 }
        $valueX = $fieldX
        if ($group -eq 3 -and $j -lt 3) { $valueX = if ($isAr) { $px+270 } else { $px+230 } }
        $g.DrawString([string]$labels[$j],$fontMeta,(New-Object System.Drawing.SolidBrush $muted),$fieldX,$py+5,$fmt)
        $g.DrawString([string]$values[$j],$fontMetaValue,$blackBrush,$valueX,$py+30,$fmt)
    }

    $itemLabels = if ($isAr) { @('البيان','الكمية','سعر الوحدة','الإجمالي') } elseif ($isMixed) { @('البيان / Description','الكمية / Qty','سعر الوحدة / Unit price','الإجمالي / Total') } else { @('Description','Qty','Unit price','Amount') }
    $tableY = if ($group -eq 1) { 800 } elseif ($group -eq 2) { 670 } elseif ($group -eq 3) { 720 } elseif ($group -eq 4) { 760 } else { 735 }
    $headerColor = if (($v % 2) -eq 0) { $accent } else { [System.Drawing.Color]::FromArgb(238,238,236) }
    $headerBrush = if (($v % 2) -eq 0) { [System.Drawing.Brushes]::White } else { New-Object System.Drawing.SolidBrush $ink }
    $g.FillRectangle((New-Object System.Drawing.SolidBrush $headerColor),65,$tableY,1110,54)
    if ($isAr) {
        $colX = @(1150,790,500,250)
    } else {
        $colX = @(85,600,820,1010)
    }
    for ($c=0; $c -lt 4; $c++) { $g.DrawString([string]$itemLabels[$c],$fontCellBold,$headerBrush,[int]$colX[$c],$tableY+16,$fmt) }

    $rowY = $tableY+54
    foreach ($lineItem in $r.line_items) {
        $description = if ($isAr) { [string]$lineItem.description_ar } elseif ($r.language -eq 'en') { [string]$lineItem.description_en } else { "$($lineItem.description_ar) / $($lineItem.description_en)" }
        if (($rowY % 2) -eq 0) { $g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(249,249,248))),65,$rowY,1110,46) }
        $g.DrawLine((New-Object System.Drawing.Pen $line,1),65,$rowY+45,1175,$rowY+45)
        $g.DrawString($description,$fontCell,$blackBrush,[int]$colX[0],$rowY+13,$fmt)
        $g.DrawString([string]$lineItem.quantity,$fontCell,$blackBrush,[int]$colX[1],$rowY+13,$fmt)
        $g.DrawString(("{0:N2}" -f [double]$lineItem.unit_price_egp),$fontCell,$blackBrush,[int]$colX[2],$rowY+13,$fmt)
        $g.DrawString(("{0:N2}" -f [double]$lineItem.line_total_egp),$fontCell,$blackBrush,[int]$colX[3],$rowY+13,$fmt)
        $rowY += 46
    }
    $sumY = $rowY+27
    $summary = if ($isAr) { @(@('الإجمالي قبل الضريبة',("{0:N2} ج.م" -f [double]$r.subtotal_egp)),@('ضريبة القيمة المضافة 14%',("{0:N2} ج.م" -f [double]$r.tax_egp)),@('الإجمالي المستحق',("{0:N2} ج.م" -f [double]$r.total_egp))) } elseif ($isMixed) { @(@('Subtotal',("{0:N2} EGP" -f [double]$r.subtotal_egp)),@('VAT 14%',("{0:N2} EGP" -f [double]$r.tax_egp)),@('Total due',("{0:N2} EGP" -f [double]$r.total_egp))) } else { @(@('Subtotal',("{0:N2} EGP" -f [double]$r.subtotal_egp)),@('VAT 14%',("{0:N2} EGP" -f [double]$r.tax_egp)),@('Total due',("{0:N2} EGP" -f [double]$r.total_egp))) }
    for ($k=0; $k -lt 3; $k++) {
        $labelX = if ($isMixed) { 650 } else { 790 }
        $amountX = if ($isAr) { 1160 } else { 970 }
        $g.DrawString([string]$summary[$k][0],$fontCell,$blackBrush,$labelX,$sumY+($k*41),$fmt)
        $g.DrawString([string]$summary[$k][1],$fontCellBold,$blackBrush,$amountX,$sumY+($k*41),$(if ($isAr) {$rtl} else {$ltr}))
    }
    $footerY = 1590
    $g.DrawLine((New-Object System.Drawing.Pen $line,1),65,$footerY,1175,$footerY)
    $g.DrawString("SYNTHETIC OCR FIXTURE - NOT FOR PAYMENT - $($r.id)",$fontNote,(New-Object System.Drawing.SolidBrush $muted),65,$footerY+18,$ltr)
    $png = Join-Path $OutputDirectory (([System.IO.Path]::GetFileNameWithoutExtension($r.file))+'.png')
    $bmp.Save($png,[System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose(); $gfont.Dispose(); $fontCell.Dispose(); $fontCellBold.Dispose()
}
$rtl.Dispose(); $ltr.Dispose()
Write-Output "Rendered $($rows.Count) varied invoice images."
