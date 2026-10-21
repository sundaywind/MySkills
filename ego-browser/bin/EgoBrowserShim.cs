using System;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Diagnostics;
using System.Security.Principal;
using System.Runtime.InteropServices;

class EgoBrowserShim {
    [DllImport("advapi32.dll", SetLastError = true)]
    static extern bool OpenProcessToken(IntPtr ProcessHandle, uint DesiredAccess, out IntPtr TokenHandle);

    [DllImport("advapi32.dll", SetLastError = true)]
    static extern bool DuplicateTokenEx(IntPtr hExistingToken, uint dwDesiredAccess, IntPtr lpTokenAttributes, int ImpersonationLevel, int TokenType, out IntPtr phNewToken);

    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessWithTokenW(IntPtr hToken, int dwLogonFlags, string lpApplicationName, string lpCommandLine, int dwCreationFlags, IntPtr lpEnvironment, string lpCurrentDirectory, ref STARTUPINFO lpStartupInfo, out PROCESS_INFORMATION lpProcessInformation);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetExitCodeProcess(IntPtr hProcess, out int lpExitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr hObject);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct STARTUPINFO {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct PROCESS_INFORMATION {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }

    static string ExtractRawArgs(string cmdLine) {
        if (string.IsNullOrEmpty(cmdLine)) return "";
        int i = 0;
        int len = cmdLine.Length;
        while (i < len && char.IsWhiteSpace(cmdLine[i])) i++;
        if (i < len && cmdLine[i] == '"') {
            i++;
            while (i < len && cmdLine[i] != '"') i++;
            if (i < len) i++;
        } else {
            while (i < len && !char.IsWhiteSpace(cmdLine[i])) i++;
        }
        while (i < len && char.IsWhiteSpace(cmdLine[i])) i++;
        return i < len ? cmdLine.Substring(i) : "";
    }

    static string ResolveRealExe() {
        string p1 = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), @".local\share\ego\active_version_dir\ego-browser.exe");
        if (File.Exists(p1)) return p1;
        string p2 = @"C:\Program Files\Citro Labs\ego lite\Application\0.6.0.16\ego-browser.exe";
        if (File.Exists(p2)) return p2;
        string appDir = @"C:\Program Files\Citro Labs\ego lite\Application";
        if (Directory.Exists(appDir)) {
            foreach (string sub in Directory.GetDirectories(appDir)) {
                string candidate = Path.Combine(sub, "ego-browser.exe");
                if (File.Exists(candidate)) return candidate;
            }
        }
        return p1;
    }

    static bool IsElevated() {
        try {
            using (WindowsIdentity id = WindowsIdentity.GetCurrent()) {
                WindowsPrincipal p = new WindowsPrincipal(id);
                return p.IsInRole(WindowsBuiltInRole.Administrator);
            }
        } catch {
            return false;
        }
    }

    static byte[] ReadStdinIfExpected(string[] args) {
        // Only read stdin when `ego-browser nodejs` is invoked WITHOUT `-e` / `--eval`
        bool isStdinNodejs = (args.Length == 1 && string.Equals(args[0], "nodejs", StringComparison.OrdinalIgnoreCase));
        if (!isStdinNodejs || !Console.IsInputRedirected) {
            return null;
        }
        try {
            Stream stdin = Console.OpenStandardInput();
            byte[] firstBuf = new byte[4096];
            Task<int> firstRead = stdin.ReadAsync(firstBuf, 0, firstBuf.Length);
            if (!firstRead.Wait(350)) {
                // No data arrived within 350ms -> empty non-TTY pipe, do not block
                return null;
            }
            int n = firstRead.Result;
            if (n <= 0) return null;
            using (MemoryStream ms = new MemoryStream()) {
                ms.Write(firstBuf, 0, n);
                byte[] buf = new byte[4096];
                int r;
                while ((r = stdin.Read(buf, 0, buf.Length)) > 0) {
                    ms.Write(buf, 0, r);
                }
                return ms.ToArray();
            }
        } catch {
            return null;
        }
    }

    static int RunDirect(string rawArgs, string workDir, byte[] stdinBytes, string outFile, string errFile) {
        string realExe = ResolveRealExe();
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = realExe;
        psi.Arguments = rawArgs;
        if (!string.IsNullOrEmpty(workDir) && Directory.Exists(workDir)) {
            psi.WorkingDirectory = workDir;
        }
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardInput = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding = Encoding.UTF8;

        StringBuilder sbOut = new StringBuilder();
        StringBuilder sbErr = new StringBuilder();

        using (Process proc = new Process()) {
            proc.StartInfo = psi;
            proc.OutputDataReceived += (s, e) => {
                if (e.Data != null) {
                    if (outFile != null) {
                        lock (sbOut) { sbOut.AppendLine(e.Data); }
                    } else {
                        Console.Out.WriteLine(e.Data);
                    }
                }
            };
            proc.ErrorDataReceived += (s, e) => {
                if (e.Data != null) {
                    if (errFile != null) {
                        lock (sbErr) { sbErr.AppendLine(e.Data); }
                    } else {
                        Console.Error.WriteLine(e.Data);
                    }
                }
            };
            proc.Start();
            try {
                if (stdinBytes != null && stdinBytes.Length > 0) {
                    proc.StandardInput.BaseStream.Write(stdinBytes, 0, stdinBytes.Length);
                    proc.StandardInput.BaseStream.Flush();
                }
                proc.StandardInput.Close();
            } catch {}
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            proc.WaitForExit();

            if (outFile != null) File.WriteAllText(outFile, sbOut.ToString(), new UTF8Encoding(false));
            if (errFile != null) File.WriteAllText(errFile, sbErr.ToString(), new UTF8Encoding(false));
            return proc.ExitCode;
        }
    }

    static int Main(string[] args) {
        Console.OutputEncoding = new UTF8Encoding(false);
        try {
            if (args.Length == 6 && args[0] == "--deelevated-worker") {
                string reqFile = args[1];
                string workDirFile = args[2];
                string stdinFile = args[3];
                string outFile = args[4];
                string errFile = args[5];
                string rawArgs = File.ReadAllText(reqFile, Encoding.UTF8);
                string workDir = File.ReadAllText(workDirFile, Encoding.UTF8);
                byte[] stdinBytes = File.Exists(stdinFile) ? File.ReadAllBytes(stdinFile) : null;
                return RunDirect(rawArgs, workDir, stdinBytes, outFile, errFile);
            }

            string currentRawArgs = ExtractRawArgs(Environment.CommandLine);
            byte[] capturedStdin = ReadStdinIfExpected(args);

            if (!IsElevated()) {
                return RunDirect(currentRawArgs, Environment.CurrentDirectory, capturedStdin, null, null);
            }

            Process[] exps = Process.GetProcessesByName("explorer");
            if (exps.Length == 0) {
                return RunDirect(currentRawArgs, Environment.CurrentDirectory, capturedStdin, null, null);
            }

            IntPtr hToken, hDupToken;
            if (!OpenProcessToken(exps[0].Handle, 0x0002 | 0x0008, out hToken)) {
                return RunDirect(currentRawArgs, Environment.CurrentDirectory, capturedStdin, null, null);
            }
            if (!DuplicateTokenEx(hToken, 0x02000000, IntPtr.Zero, 2, 1, out hDupToken)) {
                CloseHandle(hToken);
                return RunDirect(currentRawArgs, Environment.CurrentDirectory, capturedStdin, null, null);
            }

            string id = Guid.NewGuid().ToString("N");
            string tempDir = Path.GetTempPath();
            string fReq = Path.Combine(tempDir, "ego_req_" + id + ".txt");
            string fDir = Path.Combine(tempDir, "ego_dir_" + id + ".txt");
            string fIn  = Path.Combine(tempDir, "ego_in_"  + id + ".bin");
            string fOut = Path.Combine(tempDir, "ego_out_" + id + ".txt");
            string fErr = Path.Combine(tempDir, "ego_err_" + id + ".txt");

            try {
                File.WriteAllText(fReq, currentRawArgs, new UTF8Encoding(false));
                File.WriteAllText(fDir, Environment.CurrentDirectory, new UTF8Encoding(false));
                if (capturedStdin != null && capturedStdin.Length > 0) {
                    File.WriteAllBytes(fIn, capturedStdin);
                }

                string selfExe = Process.GetCurrentProcess().MainModule.FileName;
                string workerCmd = "\"" + selfExe + "\" --deelevated-worker \"" + fReq + "\" \"" + fDir + "\" \"" + fIn + "\" \"" + fOut + "\" \"" + fErr + "\"";

                STARTUPINFO si = new STARTUPINFO();
                si.cb = Marshal.SizeOf(si);
                PROCESS_INFORMATION pi;
                bool ok = CreateProcessWithTokenW(hDupToken, 0, selfExe, workerCmd, 0x08000000, IntPtr.Zero, Environment.CurrentDirectory, ref si, out pi);
                CloseHandle(hDupToken);
                CloseHandle(hToken);

                if (!ok) {
                    return RunDirect(currentRawArgs, Environment.CurrentDirectory, capturedStdin, null, null);
                }

                WaitForSingleObject(pi.hProcess, 0xFFFFFFFF);
                int exitCode = 0;
                GetExitCodeProcess(pi.hProcess, out exitCode);
                CloseHandle(pi.hProcess);
                CloseHandle(pi.hThread);

                if (File.Exists(fOut)) {
                    string o = File.ReadAllText(fOut, Encoding.UTF8);
                    if (o.Length > 0) Console.Out.Write(o);
                }
                if (File.Exists(fErr)) {
                    string e = File.ReadAllText(fErr, Encoding.UTF8);
                    if (e.Length > 0) Console.Error.Write(e);
                }
                return exitCode;
            } finally {
                try { if (File.Exists(fReq)) File.Delete(fReq); } catch {}
                try { if (File.Exists(fDir)) File.Delete(fDir); } catch {}
                try { if (File.Exists(fIn))  File.Delete(fIn);  } catch {}
                try { if (File.Exists(fOut)) File.Delete(fOut); } catch {}
                try { if (File.Exists(fErr)) File.Delete(fErr); } catch {}
            }
        } catch (Exception ex) {
            Console.Error.WriteLine("ego-browser shim error: " + ex.Message);
            return 1;
        }
    }
}