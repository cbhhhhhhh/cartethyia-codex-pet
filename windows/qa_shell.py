"""Probe the installed stdio plugin, Windows shell registration and SAPI with synthetic data."""

import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import winreg

app = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
start = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/卡提希娅/卡提希娅.lnk"
assert start.is_file()
shell = "powershell.exe"
ps = (
    lambda script, env: subprocess.check_output(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script], env=env, timeout=25
    )
    .decode("utf8")
    .strip()
)
with tempfile.TemporaryDirectory(prefix="cart-shell-") as tmp:
    local = Path(tmp)
    home = local / "codex"
    home.mkdir()
    env = dict(
        os.environ,
        LOCALAPPDATA=tmp,
        CODEX_HOME=str(home),
        CARTETHYIA_QA_LINK=str(start),
        CARTETHYIA_QA_WAV=str(local / "sapi.wav"),
    )
    link = json.loads(
        ps(
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
            "$l=(New-Object -ComObject WScript.Shell).CreateShortcut($env:CARTETHYIA_QA_LINK)\n"
            "@{target=$l.TargetPath;icon=$l.IconLocation}|ConvertTo-Json -Compress",
            env,
        )
    )
    assert Path(link["target"]) == app / "Cartethyia.exe"
    assert Path(link["icon"].rsplit(",", 1)[0]) in (app / "art/cartethyia.ico", app / "Cartethyia.exe")
    voice = ps(
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
        "$v=New-Object -ComObject SAPI.SpVoice\n"
        "$cn=$v.GetVoices()|Where-Object {$_.GetAttribute('Language') -match '804|404'}|Select-Object -First 1\n"
        "if($cn){$v.Voice=$cn}\n"
        "$s=New-Object -ComObject SAPI.SpFileStream\n"
        "$s.Open($env:CARTETHYIA_QA_WAV,3)\n$v.AudioOutputStream=$s\n"
        "[void]$v.Speak('这是一条合成语音。',16)\n$s.Close()\n$v.Voice.GetDescription()",
        env,
    )
    wav = local / "sapi.wav"
    assert wav.stat().st_size > 1000 and wav.read_bytes().startswith(b"RIFF")
    protocol = False
    for path in (
        r"Software\Classes\codex",
        r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\codex\UserChoice",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path):
                protocol = True
        except FileNotFoundError:
            pass
    if not protocol:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "codex"):
                protocol = True
        except FileNotFoundError:
            pass
    with subprocess.Popen(
        [app / "runtime/python.exe", "-X", "utf8", "-B", app / "windows/service.py", "mcp"],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    ) as mcp:

        def call(method, **params):
            mcp.stdin.write(json.dumps(dict(jsonrpc="2.0", method=method, id=1, params=params)) + "\n")
            mcp.stdin.flush()
            return json.loads(mcp.stdout.readline())["result"]

        def invoke(name, **args):
            return json.loads(call("tools/call", name=name, arguments=args)["content"][0]["text"])

        assert call("initialize")["serverInfo"]["name"] == "pet-plus"
        names = sorted(t["name"] for t in call("tools/list")["tools"])
        assert invoke("pet_status")["state"] == "idle"
        reminder = invoke(
            "pet_remind", text="折纸验收", due=datetime.datetime.now().astimezone().isoformat()
        )
        finished = invoke("pet_complete", id=reminder["id"])
        assert finished and names == ["pet_complete", "pet_remind", "pet_status"]
        mcp.stdin.close()
        assert mcp.wait(8) == 0
    assert protocol
    result = dict(
        start_menu_target=True,
        start_menu_icon=True,
        windows_codex_uri_registered=protocol,
        sapi_voice=voice,
        sapi_wav_bytes=wav.stat().st_size,
        stdio_tools_tested=names,
    )
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(result))
