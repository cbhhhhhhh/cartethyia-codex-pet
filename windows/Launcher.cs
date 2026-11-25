using System;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;
using System.Windows.Forms;

internal static class Launcher {
    [STAThread]
    private static void Main(string[] args) {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string profile = "main";
        bool quiet = false;
        for (int i = 0; i < args.Length; ++i) {
            if (args[i] == "--background") quiet = true;
            if (args[i] == "--profile" && i + 1 < args.Length && Regex.IsMatch(args[i+1], @"^[\w-]{1,32}$"))
                profile = args[++i];
        }
        try {
            var info = new ProcessStartInfo(Path.Combine(root, @"runtime\pythonw.exe"));
            info.Arguments = "-B " + "\"" + Path.Combine(root, @"windows\app.py") + "\" --profile " + profile + (quiet ? " --background" : "");
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            Process.Start(info);
        } catch (Exception e) {
            MessageBox.Show(e.Message, "Cartethyia", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}

