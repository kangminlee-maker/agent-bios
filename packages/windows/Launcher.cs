using System;
using System.Diagnostics;
using System.IO;
using System.Text;
class Launcher {
    static string Quote(string s) {
        var b = new StringBuilder("\""); int slashes = 0;
        foreach(char c in s) {
            if(c == '\\') { slashes++; continue; }
            if(c == '"') { b.Append('\\', slashes * 2 + 1); b.Append(c); }
            else { b.Append('\\', slashes); b.Append(c); }
            slashes = 0;
        }
        b.Append('\\', slashes * 2); b.Append('"'); return b.ToString();
    }
    static int Main(string[] args) {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        var command = new StringBuilder("-E -s -X utf8 " + Quote(Path.Combine(root, "package", "compose", "native_cli.py")));
        if (String.Equals(Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]), "agent-launch", StringComparison.OrdinalIgnoreCase)) command.Append(" launch");
        foreach(string arg in args) command.Append(" " + Quote(arg));
        var start = new ProcessStartInfo(Path.Combine(root, "python", "python.exe"), command.ToString());
        start.UseShellExecute = false;
        start.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        try { using(var child = Process.Start(start)) { child.WaitForExit(); return child.ExitCode; } }
        catch(Exception e) { Console.Error.WriteLine("agent-bios: " + e.Message); return 1; }
    }
}
