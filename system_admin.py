import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

import psutil


_DEFENDER_STATUS_SCRIPT = (
    "Get-MpComputerStatus | Select-Object AMServiceEnabled,AntivirusEnabled,"
    "RealTimeProtectionEnabled,AntivirusSignatureLastUpdated | ConvertTo-Json -Compress"
)
_DEFENDER_SCAN_SCRIPT = "Start-MpScan -ScanType QuickScan; Write-Output 'QUICK_SCAN_STARTED'"
_DRIVER_SEARCH_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $searcher = $session.CreateUpdateSearcher()
    $result = $searcher.Search("IsInstalled=0 and Type='Driver' and IsHidden=0")
    Write-Output ("DRIVER_UPDATES=" + $result.Updates.Count)
} catch {
    Write-Output ("UPDATE_ERROR=" + $_.Exception.Message)
    exit 1
}
"""
_DRIVER_INSTALL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $searcher = $session.CreateUpdateSearcher()
    $result = $searcher.Search("IsInstalled=0 and Type='Driver' and IsHidden=0")
    if ($result.Updates.Count -eq 0) {
        Write-Output 'DRIVER_UPDATES=0'
        exit 0
    }
    foreach ($update in $result.Updates) {
        if (-not $update.EulaAccepted) { $update.AcceptEula() }
    }
    $downloader = $session.CreateUpdateDownloader()
    $downloader.Updates = $result.Updates
    $downloadResult = $downloader.Download()
    if ($downloadResult.ResultCode -notin 2, 3) {
        throw ("Driver download failed with result code " + $downloadResult.ResultCode)
    }
    $installer = $session.CreateUpdateInstaller()
    $installer.Updates = $result.Updates
    $installResult = $installer.Install()
    Write-Output ("DRIVER_UPDATE_RESULT=" + $installResult.ResultCode)
    Write-Output ("REBOOT_REQUIRED=" + $installResult.RebootRequired)
} catch {
    Write-Output ("UPDATE_ERROR=" + $_.Exception.Message)
    exit 1
}
"""


def _run_powershell(script, timeout=60):
    if os.name != "nt":
        return None
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        return None
    try:
        return subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def get_system_status():
    memory = psutil.virtual_memory()
    drive = Path.home().anchor or os.path.abspath(os.sep)
    disk = psutil.disk_usage(drive)
    cpu_load = psutil.cpu_percent(interval=0.3)
    return (
        f"{platform.node()} is running {platform.system()} {platform.release()}. "
        f"CPU usage is {cpu_load:.0f} percent; memory usage is "
        f"{memory.percent:.0f} percent; {disk.free // (1024 ** 3)} gigabytes "
        "of drive space are free."
    )


def get_network_status():
    interfaces = psutil.net_if_stats()
    active = [name for name, stats in interfaces.items() if stats.isup and "loopback" not in name.lower()]
    counters = psutil.net_io_counters(pernic=True) or {}
    received = sum(counters[name].bytes_recv for name in active if name in counters)
    sent = sum(counters[name].bytes_sent for name in active if name in counters)
    if not active:
        return "No active network interfaces were detected on this computer."
    names = ", ".join(active[:5])
    extra = f" and {len(active) - 5} more" if len(active) > 5 else ""
    return (
        f"Network interfaces up on this computer: {names}{extra}. "
        f"Cumulative traffic: {received // (1024 ** 2)} megabytes received and "
        f"{sent // (1024 ** 2)} megabytes sent."
    )


def get_security_status():
    result = _run_powershell(_DEFENDER_STATUS_SCRIPT)
    if result is None:
        return "Windows Defender status is unavailable. I could not query the local Defender service."
    if result.returncode != 0 or not result.stdout.strip():
        return "Windows Defender status is unavailable. This does not confirm that the computer is threat-free."
    try:
        status = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return "Windows Defender returned an unreadable status. This does not confirm that the computer is threat-free."
    antivirus = "enabled" if status.get("AntivirusEnabled") else "disabled"
    realtime = "enabled" if status.get("RealTimeProtectionEnabled") else "disabled"
    signature_time = status.get("AntivirusSignatureLastUpdated") or "unknown"
    return (
        f"Microsoft Defender antivirus is {antivirus}; real-time protection is {realtime}; "
        f"the latest signature timestamp is {signature_time}. This status check is not a threat scan."
    )


def start_security_scan():
    result = _run_powershell(_DEFENDER_SCAN_SCRIPT, timeout=120)
    if result is None or result.returncode != 0:
        return "I could not start a Microsoft Defender quick scan. Check Defender availability and permissions."
    return "Microsoft Defender quick scan started. Windows Security will show the scan results."


def _driver_update_count():
    result = _run_powershell(_DRIVER_SEARCH_SCRIPT, timeout=900)
    if result is None or result.returncode != 0:
        return None, "Windows Update driver status is unavailable."
    match = re.search(r"DRIVER_UPDATES=(\d+)", result.stdout)
    if not match:
        return None, "Windows Update returned an unreadable driver update status."
    return int(match.group(1)), None


def check_for_updates():
    driver_count, driver_error = _driver_update_count()
    winget = shutil.which("winget.exe") or shutil.which("winget")
    if not winget:
        software_summary = "winget is not installed, so software update status is unavailable."
    else:
        try:
            result = subprocess.run(
                [winget, "upgrade", "--accept-source-agreements", "--disable-interactivity"],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            lines = [line.strip() for line in (result.stdout or result.stderr).splitlines() if line.strip()]
            summary = next((line for line in reversed(lines) if "available" in line.lower()), "")
            software_summary = f"winget: {summary}" if summary else "winget update check completed."
        except (OSError, subprocess.TimeoutExpired):
            software_summary = "winget software update check failed or timed out."
    if driver_error:
        driver_summary = driver_error
    else:
        driver_summary = f"Windows Update found {driver_count} available driver update(s)."
    return f"{driver_summary} {software_summary}"


def install_updates():
    driver_result = _run_powershell(_DRIVER_INSTALL_SCRIPT, timeout=3600)
    if driver_result is None:
        driver_summary = "Windows driver updates could not be started."
    elif driver_result.returncode != 0:
        driver_summary = "Windows driver updates failed. Check Windows Update for details."
    else:
        result_code = re.search(r"DRIVER_UPDATE_RESULT=(\d+)", driver_result.stdout)
        if "DRIVER_UPDATES=0" in driver_result.stdout:
            driver_summary = "No Windows driver updates were available."
        elif result_code and result_code.group(1) in {"2", "3"}:
            reboot = " A restart is required." if "REBOOT_REQUIRED=True" in driver_result.stdout else ""
            driver_summary = f"Windows driver updates installed.{reboot}"
        else:
            driver_summary = "Windows driver update status is unclear; check Windows Update."

    winget = shutil.which("winget.exe") or shutil.which("winget")
    if not winget:
        software_summary = "winget is not installed, so software was not updated."
    else:
        try:
            result = subprocess.run(
                [
                    winget,
                    "upgrade",
                    "--all",
                    "--silent",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                    "--disable-interactivity",
                ],
                capture_output=True,
                text=True,
                timeout=3600,
                check=False,
            )
            if result.returncode == 0:
                software_summary = "winget software update run completed."
            else:
                software_summary = f"winget software update run returned code {result.returncode}."
        except subprocess.TimeoutExpired:
            software_summary = "winget software update run timed out."
        except OSError:
            software_summary = "winget could not be started, so software was not updated."
    return f"{driver_summary} {software_summary}"


def handle_system_command(text):
    command = re.sub(r"[\s.,!?]+$", "", text.strip().lower())
    if command in {"system status", "check system health", "hardware status", "monitor hardware"}:
        return get_system_status()
    if command in {"network status", "check my network", "monitor my network"}:
        return get_network_status()
    if command in {"security status", "check security"}:
        return get_security_status()
    if command in {"scan for threats", "run security scan", "start security scan"}:
        return start_security_scan()
    if command in {"check for updates", "check drivers and software updates"}:
        return check_for_updates()
    if command in {
        "update drivers and software",
        "update my drivers and software",
        "update software and drivers",
        "install updates",
    }:
        return install_updates()
    return None