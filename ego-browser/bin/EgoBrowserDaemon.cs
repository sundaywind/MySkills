using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;

/// <summary>
/// EgoBrowser 独立常驻后台守护进程：
/// 运行于普通用户桌面会话下，监听 %TEMP%\ego_shim_daemon_queue 目录中的命令请求文件，
/// 解决管理员（Elevated）终端或沙箱环境下调用 ego-browser 时的权限隔离与会话通信问题。
/// </summary>
class EgoBrowserDaemon {
    /// <summary>
    /// 解析本地真实安装的 ego-browser.exe 路径
    /// </summary>
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

    /// <summary>
    /// 直接启动真实的 ego-browser.exe 执行命令，并捕获标准输出/错误写入队列结果文件
    /// </summary>
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
        psi.WindowStyle = ProcessWindowStyle.Hidden;
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
                    lock (sbOut) { sbOut.AppendLine(e.Data); }
                }
            };
            proc.ErrorDataReceived += (s, e) => {
                if (e.Data != null) {
                    lock (sbErr) { sbErr.AppendLine(e.Data); }
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

    /// <summary>
    /// 获取或创建进程间文件队列通信目录（%TEMP%\ego_shim_daemon_queue）
    /// </summary>
    static string GetQueueDir() {
        string d = Path.Combine(Path.GetTempPath(), "ego_shim_daemon_queue");
        if (!Directory.Exists(d)) Directory.CreateDirectory(d);
        return d;
    }

    /// <summary>
    /// 守护进程主入口：通过命名互斥体保证单实例运行，轮询处理 .ready 请求文件并异步执行
    /// </summary>
    [STAThread]
    static void Main() {
        bool createdNew;
        using (Mutex m = new Mutex(true, @"Local\EgoBrowserShimDaemonMutex", out createdNew)) {
            if (!createdNew) return;
            string qDir = GetQueueDir();
            while (true) {
                try {
                    string[] readyFiles = Directory.GetFiles(qDir, "*.ready");
                    foreach (string rFile in readyFiles) {
                        string id = Path.GetFileNameWithoutExtension(rFile);
                        try { File.Delete(rFile); } catch { continue; }
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
}