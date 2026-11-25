[Setup]
AppId={{4B5A08E3-1FB6-40AC-B847-3F96BDBA4CF2}
AppName=卡提希娅 Codex 桌宠
AppVersion=2.2.0
AppPublisher=Cartethyia Codex Pet
DefaultDirName={localappdata}\Programs\CartethyiaPet
DefaultGroupName=卡提希娅
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=Cartethyia-2.2.0-Windows-x64-Setup
SetupIconFile=..\art\cartethyia.ico
UninstallDisplayIcon={app}\Cartethyia.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=no
UninstallLogMode=append
[Files]
Source: "..\.build\windows-app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "runtime\*,__pycache__\*,*.pyc"
#include "..\.build\runtime-files.iss"
[Icons]
Name: "{group}\卡提希娅"; Filename: "{app}\Cartethyia.exe"; IconFilename: "{app}\art\cartethyia.ico"
Name: "{group}\安装与使用说明"; Filename: "{app}\docs\WINDOWS.md"
Name: "{group}\卸载卡提希娅"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\runtime\python.exe"; Parameters: "-B ""{app}\windows\service.py"" register"; Flags: runhidden waituntilterminated
Filename: "{app}\Cartethyia.exe"; Parameters: "--background"; Flags: nowait
[Messages]
SetupWindowTitle=安装卡提希娅
WelcomeLabel1=欢迎安装卡提希娅 Codex 桌宠
WelcomeLabel2=将在当前用户的桌面安装卡提希娅。安装完成后，她会出现在桌面；聊天模型可以在设置中下载。
ButtonNext=下一步(&N) >
ButtonBack=< 上一步(&B)
ButtonInstall=安装(&I)
ButtonCancel=取消
ButtonFinish=完成(&F)
SelectDirLabel3=卡提希娅将安装到下列文件夹。
WizardSelectDir=选择安装位置
WizardReady=准备安装
ReadyLabel1=安装程序已准备好安装卡提希娅。
WizardInstalling=正在安装
FinishedHeadingLabel=安装完成
FinishedLabel=卡提希娅已安装到本机。可通过开始菜单或托盘打开设置。
[Code]
var
  HadApp, InstalledOK: Boolean;

function NeedsRuntimeFile(const RelativeName, Digest: String): Boolean;
var Dest: String;
begin
  Dest := ExpandConstant('{app}\') + RelativeName;
  Result := not FileExists(Dest);
  if not Result then
    Result := CompareText(GetSHA256OfFile(Dest), Digest) <> 0;
end;

procedure StopProjectMCP();
var Locator, Services, Processes, Worker: Variant;
    I: Integer;
    PythonPath, WorkerPath, Helper, Cmd: String;
begin
  PythonPath := Lowercase(ExpandConstant('{app}\runtime\python.exe'));
  Helper := Lowercase(ExpandConstant('{app}\windows\service.py'));
  Locator := CreateOleObject('WbemScripting.SWbemLocator');
  Services := Locator.ConnectServer('.', 'root\CIMV2');
  Processes := Services.ExecQuery('select * from Win32_Process where Name=''python.exe'' and ExecutablePath is not null and CommandLine is not null');
  for I := 0 to Processes.Count - 1 do begin
    Worker := Processes.ItemIndex(I);
    WorkerPath := Worker.ExecutablePath;
    if CompareText(WorkerPath, PythonPath) = 0 then begin
      Cmd := Worker.CommandLine;
      Cmd := Lowercase(Trim(Cmd));
      if (Pos(Helper, Cmd) > 0) and (Copy(Cmd, Length(Cmd)-3, 4) = ' mcp') then begin
        Log('Closing Cartethyia stdio MCP PID ' + IntToStr(Worker.ProcessId));
        Worker.Terminate(0);
      end;
    end;
  end;
end;

function RunService(const Command: String; var Code: Integer): Boolean;
begin
  Result := Exec(ExpandConstant('{app}\runtime\python.exe'), '-B "' + ExpandConstant('{app}\windows\service.py') + '" ' + Command, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  HadApp := FileExists(ExpandConstant('{app}\windows\service.py'));
  if HadApp then begin
    RunService('shutdown', Code);
    Sleep(1000);
    StopProjectMCP();
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then InstalledOK := True;
end;

procedure DeinitializeSetup();
var Code: Integer;
begin
  if HadApp and not InstalledOK and FileExists(ExpandConstant('{app}\Cartethyia.exe')) then
    Exec(ExpandConstant('{app}\Cartethyia.exe'), '--background', '', SW_HIDE, ewNoWait, Code);
end;

function InitializeUninstall(): Boolean;
var Code: Integer;
begin
  Result := RunService('unregister', Code) and (Code = 0);
  if not Result then begin
    MsgBox('Codex 插件注销失败。请检查 Codex CLI 或桌宠数据目录的 connection.json，再重试卸载。', mbError, MB_OK);
    exit;
  end;
  RunService('shutdown', Code);
  Sleep(1000);
  StopProjectMCP();
end;

