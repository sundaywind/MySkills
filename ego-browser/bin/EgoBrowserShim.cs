using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;
using System.Security.Principal;
using System.Runtime.InteropServices;

/// <summary>
/// EgoBrowser 命令行包装器（Shim）：
/// 拦截 CLI 调用参数与标准输入，通过计划任务（EgoBrowserShimDaemon）确保后台守护进程运行，
/// 并将请求投递至 %TEMP%\ego_shim_daemon_queue 文件队列，等待执行完成后回传标准输出与退出码。
/// </summary>
class EgoBrowserShim {
    [DllImport("advapi32.dll", SetLastError = true)]
    static extern bool OpenProcessToken(IntPtr ProcessHandle, uint DesiredAccess, out IntPtr TokenHandle);

    [DllImport("advapi32.dll", SetLastError = true)]
    static extern bool DuplicateTokenEx(IntPtr hExistingToken, uint dwDesiredAccess, IntPtr lpTokenAttributes, int ImpersonationLevel, int TokenType, out IntPtr phNewToken);

    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessWithTokenW(IntPtr hToken, int dwLogonFlags, string lpApplicationName, string lpCommandLine, int dwCreationFlags, IntPtr lpEnvironment, string lpCurrentDirectory, ref STARTUPINFO lpStartupInfo, out PROCESS_INFORMATION lpProcessInformation);

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
        bool isStdinNodejs = (args.Length == 1 && string.Equals(args[0], "nodejs", StringComparison.OrdinalIgnoreCase));
        if (!isStdinNodejs || !Console.IsInputRedirected) {
            return null;
        }
        try {
            Stream stdin = Console.OpenStandardInput();
            byte[] firstBuf = new byte[4096];
            Task<int> firstRead = stdin.ReadAsync(firstBuf, 0, firstBuf.Length);
            if (!firstRead.Wait(350)) {
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

    static string GetQueueDir() {
        string d = Path.Combine(Path.GetTempPath(), "ego_shim_daemon_queue");
        if (!Directory.Exists(d)) Directory.CreateDirectory(d);
        return d;
    }

    static void RunDaemonLoop() {
        bool createdNew;
        using (Mutex m = new Mutex(true, @"Local\EgoBrowserShimDaemonMutex", out createdNew)) {
            if (!createdNew) return;
            string qDir = GetQueueDir();
            while (true) {
                try {
                    string[] readyFiles = Directory.GetFiles(qDir, "*.ready");
                    foreach (string rFile in readyFiles) {
                        string id = Path.GetFileNameWithoutExtension(rFile);
                        File.Delete(rFile);
                        Task.Run(() => {
                            try {
                                string fReq = Path.Combine(qDir, id + ".req");
                                string fDir = Path.Combine(qDir, id + ".dir");
                                string fIn  = Path.Combine(qDir, id + ".in");
                                string fOut = Path.Combine(qDir, id + ".out");
                                string fErr = Path.Combine(qDir, id + ".err");
                                string fDone = Path.Combine(qDir, id + ".done");
                                string rawArgs = File.ReadAllText(fReq, Encoding.UTF8);
                                string workDir = File.ReadAllText(fDir, Encoding.UTF8);
                                byte[] stdinBytes = File.Exists(fIn) ? File.ReadAllBytes(fIn) : null;
                                int code = RunDirect(rawArgs, workDir, stdinBytes, fOut, fErr);
                                File.WriteAllText(fDone, code.ToString(), Encoding.ASCII);
                            } catch (Exception ex) {
                                try {
                                    File.WriteAllText(Path.Combine(qDir, id + ".err"), ex.Message, new UTF8Encoding(false));
                                    File.WriteAllText(Path.Combine(qDir, id + ".done"), "1", Encoding.ASCII);
                                } catch {}
                            }
                        });
                    }
                } catch {}
                Thread.Sleep(25);
            }
        }
    }

    /// <summary>
    /// 检测后台守护进程互斥体是否存在；若未运行，则通过 schtasks 唤醒计划任务启动守护进程
    /// </summary>
    static void EnsureDaemonRunning() {
        bool exists = false;
        try {
            using (Mutex m = Mutex.OpenExisting(@"Local\EgoBrowserShimDaemonMutex")) {
                exists = true;
            }
        } catch {
            exists = false;
        }
        if (exists) return;

        string selfExe = Process.GetCurrentProcess().MainModule.FileName;
        string daemonCmd = "\"" + selfExe + "\" --daemon-loop";

        try {
            ProcessStartInfo psi = new ProcessStartInfo("schtasks.exe", "/Run /TN \"EgoBrowserShimDaemon\"");
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            using (Process p = Process.Start(psi)) { p.WaitForExit(3000); }
        } catch {}
        for (int i = 0; i < 40; i++) {
            try {
                using (Mutex m = Mutex.OpenExisting(@"Local\EgoBrowserShimDaemonMutex")) {
                    return;
                }
            } catch {
                Thread.Sleep(25);
            }
        }
    }

    /// <summary>
    /// Shim 主入口：生成唯一请求 ID，写入参数与 stdin 到临时队列，轮询等待 .done 完成标志并输出结果
    /// </summary>
    static int Main(string[] args) {
        Console.OutputEncoding = new UTF8Encoding(false);
        try {
            if (args.Length == 1 && args[0] == "--daemon-loop") {
                RunDaemonLoop();
                return 0;
            }

            string currentRawArgs = ExtractRawArgs(Environment.CommandLine);
            byte[] capturedStdin = ReadStdinIfExpected(args);

            EnsureDaemonRunning();

            string qDir = GetQueueDir();
            string id = Guid.NewGuid().ToString("N");
            string fReq  = Path.Combine(qDir, id + ".req");
            string fDir  = Path.Combine(qDir, id + ".dir");
            string fIn   = Path.Combine(qDir, id + ".in");
            string fOut  = Path.Combine(qDir, id + ".out");
            string fErr  = Path.Combine(qDir, id + ".err");
            string fRdy  = Path.Combine(qDir, id + ".ready");
            string fDone = Path.Combine(qDir, id + ".done");

            try {
                File.WriteAllText(fReq, currentRawArgs, new UTF8Encoding(false));
                File.WriteAllText(fDir, Environment.CurrentDirectory, new UTF8Encoding(false));
                if (capturedStdin != null && capturedStdin.Length > 0) {
                    File.WriteAllBytes(fIn, capturedStdin);
                }
                File.WriteAllText(fRdy, "1", Encoding.ASCII);

                while (!File.Exists(fDone)) {
                    Thread.Sleep(25);
                }

                int exitCode = 0;
                int.TryParse(File.ReadAllText(fDone, Encoding.ASCII).Trim(), out exitCode);

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
                try { if (File.Exists(fReq))  File.Delete(fReq);  } catch {}
                try { if (File.Exists(fDir))  File.Delete(fDir);  } catch {}
                try { if (File.Exists(fIn))   File.Delete(fIn);   } catch {}
                try { if (File.Exists(fOut))  File.Delete(fOut);  } catch {}
                try { if (File.Exists(fErr))  File.Delete(fErr);  } catch {}
                try { if (File.Exists(fRdy))  File.Delete(fRdy);  } catch {}
                try { if (File.Exists(fDone)) File.Delete(fDone); } catch {}
            }
        } catch (Exception ex) {
            Console.Error.WriteLine("ego-browser shim error: " + ex.Message);
            return 1;
        }
    }
}