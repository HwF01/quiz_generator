#define MyAppName "智能题库生成器"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Fastload"
#define MyAppExeName "launcher.py"

#ifndef PayloadDir
  #define PayloadDir "dist\payload"
#endif

[Setup]
AppId={{A3E91C4B-7D2F-4E18-9B6A-81C4F0D1E2A7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\QuizGen
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=QuizGen-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
#if FileExists("quizgen.ico")
SetupIconFile=quizgen.ico
#endif
UninstallDisplayIcon={app}\quizgen.ico
UninstallDisplayName={#MyAppName}
ChangesEnvironment=no
CloseApplications=yes
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"; Flags: unchecked

[Components]
Name: "main"; Description: "核心程序（必装）"; Types: full compact custom; Flags: fixed
#if DirExists("dist\ocr-payload")
Name: "ocr"; Description: "扫描件 OCR（Tesseract 中英文，体积较大）"; Types: full
#endif

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs
#if DirExists("dist\ocr-payload")
Source: "dist\ocr-payload\*"; DestDir: "{app}\runtime\tesseract"; Components: ocr; Flags: ignoreversion recursesubdirs createallsubdirs
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; Comment: "{#MyAppName}"; IconFilename: "{app}\quizgen.ico"
Name: "{group}\{#MyAppName}（显示日志）"; Filename: "{app}\runtime\python\python.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\quizgen.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\quizgen.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app\backend\__pycache__"

[Code]
var
  ModePage: TInputOptionWizardPage;
  KeyPage: TInputQueryWizardPage;

function GenerateSecret: String;
var
  Seed: String;
begin
  Seed := GetDateTimeString('yyyymmddhhnnsszzz', #0, #0) +
    ExpandConstant('{computername}{username}{app}') +
    IntToStr(Random(2147483647));
  Result := GetSHA1OfString(Seed) + GetSHA1OfString(Seed + 'quizgen');
end;

procedure InitializeWizard;
begin
  ModePage := CreateInputOptionPage(wpSelectTasks,
    '出题方式', '选择大模型',
    '没有 API Key 时可以使用演示模式（题目为占位，不调用网络模型）。密钥只保存在你的用户目录。',
    True, False);
  ModePage.Add('演示模式（无需 Key，可稍后在数据目录修改）');
  ModePage.Add('通义千问 Qwen');
  ModePage.Add('DeepSeek');
  ModePage.SelectedValueIndex := 0;

  KeyPage := CreateInputQueryPage(ModePage.ID,
    'API Key', '填写密钥',
    '演示模式可留空。请使用你自己的 Key，安装包不会预置任何密钥。');
  KeyPage.Add('API Key:', False);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = KeyPage.ID then
    Result := ModePage.SelectedValueIndex = 0;
end;

procedure WriteUserConfig;
var
  ConfigDir, ConfigFile, Secret, Key, Mock, Qwen, Deepseek, Ocr: String;
  Lines: TArrayOfString;
begin
  ConfigDir := ExpandConstant('{userappdata}\QuizGen');
  ForceDirectories(ConfigDir);
  ConfigFile := ConfigDir + '\config.env';
  if FileExists(ConfigFile) then
    Exit;

  Secret := GenerateSecret;
  Key := Trim(KeyPage.Values[0]);
  Mock := 'true';
  Qwen := '';
  Deepseek := '';
  if ModePage.SelectedValueIndex = 1 then
  begin
    Mock := 'false';
    Qwen := Key;
  end;
  if ModePage.SelectedValueIndex = 2 then
  begin
    Mock := 'false';
    Deepseek := Key;
  end;

  Ocr := 'false';
#if DirExists("dist\ocr-payload")
  if WizardIsComponentSelected('ocr') then
    Ocr := 'true';
#endif

  SetArrayLength(Lines, 24);
  Lines[0] := '# 智能题库生成器 — 本机配置（不要分享含有 API Key 的文件）';
  Lines[1] := 'APP_NAME=智能题库生成器';
  Lines[2] := 'APP_ENV=desktop';
  Lines[3] := 'SECRET_KEY=' + Secret;
  Lines[4] := 'DATABASE_URL=sqlite+aiosqlite:///./quizgen.db';
  Lines[5] := 'REDIS_URL=memory://';
  Lines[6] := 'FRONTEND_URL=http://127.0.0.1:3000';
  Lines[7] := 'MOCK_LLM=' + Mock;
  Lines[8] := 'ENABLE_OCR=' + Ocr;
  Lines[9] := 'QWEN_API_KEY=' + Qwen;
  Lines[10] := 'QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1';
  Lines[11] := 'QWEN_MODEL=qwen-plus';
  Lines[12] := 'DEEPSEEK_API_KEY=' + Deepseek;
  Lines[13] := 'DEEPSEEK_BASE_URL=https://api.deepseek.com';
  Lines[14] := 'DEEPSEEK_MODEL=deepseek-chat';
  Lines[15] := 'ANTHROPIC_API_KEY=';
  Lines[16] := 'OPENAI_API_KEY=';
  Lines[17] := 'EMBEDDING_PROVIDER=local';
  Lines[18] := 'EMBEDDING_MODEL=hashed-bigram';
  Lines[19] := 'DAILY_GEN_QUOTA=20';
  Lines[20] := 'ACCESS_TOKEN_EXPIRE_MINUTES=10080';
  Lines[21] := 'MAX_UPLOAD_MB=20';
  Lines[22] := 'SETUP_COMPLETE=true';
  Lines[23] := '';
  SaveStringsToFile(ConfigFile, Lines, True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteUserConfig;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('是否同时删除本地数据（题库、上传文件、配置）？选择「否」可保留 %APPDATA%\QuizGen。',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\QuizGen'), True, True, True);
  end;
end;
