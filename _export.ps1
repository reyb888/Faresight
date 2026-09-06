$ppt = New-Object -ComObject PowerPoint.Application
$pres = $ppt.Presentations.Open('D:\Computer Science\Hackathons\SIH 2026\Faresight\Skyraxis_SIH2026_Faresight_Winning.pptx')
$outFolder = 'D:\Computer Science\Hackathons\SIH 2026\Faresight\_slide_preview'
if (-not (Test-Path $outFolder)) { New-Item -ItemType Directory -Path $outFolder }
$pres.SaveAs($outFolder, 17)
$pres.Close()
$ppt.Quit()
