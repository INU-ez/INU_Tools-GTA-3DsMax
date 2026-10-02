# Build with an extracted SDK and compiler, without installing either package.
param(
    [Parameter(Mandatory=$true)][ValidateSet(2023,2024,2025,2026)][int] $Year,
    [Parameter(Mandatory=$true)][string] $SdkPath,
    [Parameter(Mandatory=$true)][string] $ToolsPath,
    [string] $WindowsSdkPath = 'C:/Program Files (x86)/Windows Kits/10',
    [string] $WindowsSdkVersion = '10.0.22621.0'
)
$ErrorActionPreference = 'Stop'
$sdkRoot = (Resolve-Path -LiteralPath $SdkPath).Path
$compilerRoot = (Resolve-Path -LiteralPath $ToolsPath).Path
$compilerBin = Join-Path $compilerRoot 'bin/Hostx64/x64'
$objRoot = Join-Path $PSScriptRoot "obj/$Year"
$outRoot = Join-Path $PSScriptRoot "bin/$Year"
New-Item -ItemType Directory -Path $objRoot,$outRoot -Force | Out-Null
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    $env:INCLUDE = "$compilerRoot/include;$compilerRoot/atlmfc/include;$sdkRoot/include;$WindowsSdkPath/Include/$WindowsSdkVersion/ucrt;$WindowsSdkPath/Include/$WindowsSdkVersion/shared;$WindowsSdkPath/Include/$WindowsSdkVersion/um"
    $env:LIB = "$compilerRoot/lib/x64;$compilerRoot/lib/onecore/x64;$compilerRoot/atlmfc/lib/x64;$sdkRoot/lib/x64/Release;$WindowsSdkPath/Lib/$WindowsSdkVersion/ucrt/x64;$WindowsSdkPath/Lib/$WindowsSdkVersion/um/x64"
    $defines = @('WIN32','WIN64','_WINDOWS','_USRDLL','NDEBUG','UNICODE','_UNICODE',
                 'WIN32_LEAN_AND_MEAN','NOMINMAX','_ADESK_3DSMAX_WINDOWS_',
                 'WINVER=0x0601','_WIN32_WINNT=0x0601','_CRT_SECURE_NO_DEPRECATE',
                 '_CRT_NONSTDC_NO_DEPRECATE','_SCL_SECURE_NO_DEPRECATE',
                 'ISOLATION_AWARE_ENABLED=1')
    $standard = if ($Year -ge 2026) { '/std:c++20' } else { '/std:c++17' }
    foreach ($source in @('INU_Import','INU_FastMesh')) {
        $objFile = Join-Path $objRoot "$source.obj"
        $arguments = @('/nologo','/c',$standard,'/EHa','/MD','/O2','/GR',
                       '/Zc:__cplusplus','/Zc:lambda','/Zc:inline','/permissive-',"/Fo$objFile") +
                     @($defines | ForEach-Object { '/D' + $_ }) +
                     @(Join-Path $PSScriptRoot "$source.cpp")
        & (Join-Path $compilerBin 'cl.exe') @arguments
        if ($LASTEXITCODE -ne 0) { throw "$source compilation failed for $Year" }
    }
    & (Join-Path $compilerBin 'link.exe') /NOLOGO /DLL /SUBSYSTEM:WINDOWS "/OUT:$outRoot/INU_Import.dli" "$objRoot/INU_Import.obj" "$objRoot/INU_FastMesh.obj" core.lib maxutil.lib geom.lib mesh.lib paramblk2.lib maxscrpt.lib user32.lib
    if ($LASTEXITCODE -ne 0) { throw "Link failed for $Year" }
    Write-Output "Built: $outRoot/INU_Import.dli"
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
