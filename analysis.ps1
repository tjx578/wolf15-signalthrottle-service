[CmdletBinding()]
param(
    [string]$Symbol = "NZDCHF",
    [int]$HardGapSec = 300,
    [int]$ContinuityGapSec = 90,
    [string]$ApiBase = "https://wolf15-signalthrottle-service-production.up.railway.app",
    [string[]]$RawLogLines = @()
)

function Get-TimestampsFromApi {
    param(
        [string]$ApiBase,
        [string]$Symbol
    )

    $response = Invoke-RestMethod -Uri "$ApiBase/signals/history?symbol=$Symbol&limit=200"
    $signals = @($response.signals)

    return $signals |
        ForEach-Object {
            if ($_.end_utc) { $_.end_utc }
            elseif ($_.signal_end_utc) { $_.signal_end_utc }
            elseif ($_.timestamp_utc) { $_.timestamp_utc }
            else { $_.signal_time }
        } |
        Where-Object { $_ } |
        Sort-Object |
        ForEach-Object { [DateTime]$_ }
}

function Get-TimestampsFromLogs {
    param([string[]]$Lines)

    return $Lines |
        Where-Object { $_ -match '"timestamp"\s*:\s*"([^"]+)"' } |
        ForEach-Object { [DateTime]$matches[1] } |
        Sort-Object
}

function Get-Clusters {
    param(
        [datetime[]]$Times,
        [int]$MaxGapSec
    )

    if (-not $Times -or $Times.Count -eq 0) {
        return @()
    }

    $clusters = @()
    $currentCluster = [PSCustomObject]@{
        Start = $Times[0]
        End = $Times[0]
        Count = 1
        Times = @($Times[0])
    }

    for ($i = 1; $i -lt $Times.Count; $i++) {
        $gap = ($Times[$i] - $Times[$i - 1]).TotalSeconds
        if ($gap -le $MaxGapSec) {
            $currentCluster.End = $Times[$i]
            $currentCluster.Count++
            $currentCluster.Times += $Times[$i]
        }
        else {
            $clusters += $currentCluster
            $currentCluster = [PSCustomObject]@{
                Start = $Times[$i]
                End = $Times[$i]
                Count = 1
                Times = @($Times[$i])
            }
        }
    }

    $clusters += $currentCluster
    return $clusters
}

function Get-PressureGrade {
    param(
        [double]$DurationMin,
        [int]$Count,
        [double]$Density,
        [double]$MaxGapSec
    )

    if ($DurationMin -lt 5) { return "FAILED_MIN_DURATION" }
    if ($MaxGapSec -gt 300) { return "REJECT" }
    if ($DurationMin -ge 20 -and $Count -ge 150 -and $Density -ge 7 -and $MaxGapSec -le 60) { return "A+" }
    if ($DurationMin -ge 14 -and $Count -ge 100 -and $Density -ge 7 -and $MaxGapSec -le 60) { return "A" }
    if ($DurationMin -ge 10 -and $Density -ge 7 -and $MaxGapSec -le 60) { return "A-" }
    if ($DurationMin -ge 5 -and $Density -ge 5 -and $MaxGapSec -le 90) { return "B+" }
    return "C"
}

function Measure-Clusters {
    param([object[]]$Clusters)

    $results = @()
    foreach ($cluster in $Clusters) {
        $durationMin = ($cluster.End - $cluster.Start).TotalMinutes
        $density = if ($durationMin -gt 0) { $cluster.Count / $durationMin } else { 0 }
        $maxGap = 0.0

        for ($i = 1; $i -lt $cluster.Times.Count; $i++) {
            $gap = ($cluster.Times[$i] - $cluster.Times[$i - 1]).TotalSeconds
            if ($gap -gt $maxGap) {
                $maxGap = $gap
            }
        }

        $results += [PSCustomObject]@{
            Start = $cluster.Start.ToString("yyyy-MM-dd HH:mm:ss")
            End = $cluster.End.ToString("yyyy-MM-dd HH:mm:ss")
            Count = $cluster.Count
            DurationMin = [Math]::Round($durationMin, 2)
            Density = [Math]::Round($density, 2)
            MaxGapSec = [Math]::Round($maxGap, 2)
            Grade = Get-PressureGrade -DurationMin $durationMin -Count $cluster.Count -Density $density -MaxGapSec $maxGap
            Times = $cluster.Times
        }
    }

    return $results
}

function Get-BestValidGrade {
    param([object[]]$MeasuredClusters)

    $rank = @{ "B+" = 2; "A-" = 3; "A" = 4; "A+" = 5 }
    $valid = $MeasuredClusters | Where-Object { $rank.ContainsKey($_.Grade) }
    if (-not $valid) {
        return $null
    }

    return ($valid | Sort-Object { $rank[$_.Grade] } -Descending | Select-Object -First 1).Grade
}

if ($RawLogLines.Count -gt 0) {
    $times = Get-TimestampsFromLogs -Lines $RawLogLines
}
else {
    $times = Get-TimestampsFromApi -ApiBase $ApiBase -Symbol $Symbol
}

if (-not $times -or $times.Count -eq 0) {
    Write-Host "No $Symbol data found."
    return
}

$seriesClusters = Get-Clusters -Times $times -MaxGapSec $HardGapSec
$seriesAnalysis = foreach ($series in $seriesClusters) {
    $continuityClusters = Get-Clusters -Times $series.Times -MaxGapSec $ContinuityGapSec
    $continuityAnalysis = Measure-Clusters -Clusters $continuityClusters

    [PSCustomObject]@{
        SeriesStart = $series.Start.ToString("yyyy-MM-dd HH:mm:ss")
        SeriesEnd = $series.End.ToString("yyyy-MM-dd HH:mm:ss")
        SeriesCount = $series.Count
        SeriesDurationMin = [Math]::Round(($series.End - $series.Start).TotalMinutes, 2)
        SeriesReason = if ($continuityAnalysis.Count -gt 1) { "SPLIT_BY_CONTINUITY_GAP" } else { "CONTINUOUS_PRESSURE_SERIES" }
        BestValidBlockGrade = Get-BestValidGrade -MeasuredClusters $continuityAnalysis
        BlocksMerged = $continuityAnalysis.Count
        Blocks = $continuityAnalysis
    }
}

$seriesAnalysis |
    Select-Object SeriesStart, SeriesEnd, SeriesCount, SeriesDurationMin, SeriesReason, BestValidBlockGrade, BlocksMerged |
    Format-Table

foreach ($series in $seriesAnalysis) {
    Write-Host "`nSeries $($series.SeriesStart) -> $($series.SeriesEnd)"
    $series.Blocks |
        Select-Object Start, End, Count, DurationMin, Density, MaxGapSec, Grade |
        Format-Table
}
