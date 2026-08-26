using System.Diagnostics;
using System.IO;
using System.Text.Json.Nodes;

namespace JerseyModder.Wpf.Services;

public sealed class TrimWebSessionService : IDisposable
{
    private readonly string _projectRoot;
    private Process? _process;
    public string? Url { get; private set; }
    public string? StatePath { get; private set; }

    public TrimWebSessionService(string projectRoot) => _projectRoot = projectRoot;

    public async Task<string> StartAsync(string referencePath, CancellationToken cancellationToken = default)
    {
        Stop();
        var folder = Path.Combine(Path.GetTempPath(), "nba2k_jersey_modder", "wpf_trim_web", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        StatePath = Path.Combine(folder, "state.json");
        var process = new Process { StartInfo = new ProcessStartInfo
        {
            FileName = FindPython(_projectRoot), WorkingDirectory = _projectRoot,
            UseShellExecute = false, RedirectStandardOutput = true,
            RedirectStandardError = true, CreateNoWindow = true,
        }};
        process.StartInfo.ArgumentList.Add("-u");
        process.StartInfo.ArgumentList.Add(Path.Combine(_projectRoot, "tools", "wpf_trim_web.py"));
        process.StartInfo.ArgumentList.Add("--reference"); process.StartInfo.ArgumentList.Add(referencePath);
        process.StartInfo.ArgumentList.Add("--state"); process.StartInfo.ArgumentList.Add(StatePath);
        process.Start(); _process = process; _ = DrainErrorsAsync(process);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        var line = await process.StandardOutput.ReadLineAsync(timeout.Token) ?? throw new InvalidOperationException("The trim web selector did not start.");
        Url = JsonNode.Parse(line)?["url"]?.GetValue<string>() ?? throw new InvalidDataException("The trim web selector returned an invalid address.");
        OpenSelector(); return Url;
    }

    public void OpenSelector() => OpenPath(string.Empty);
    public void OpenEditor() => OpenPath("edit");
    private void OpenPath(string relative)
    {
        if (string.IsNullOrWhiteSpace(Url)) throw new InvalidOperationException("Upload a jersey mockup first.");
        Process.Start(new ProcessStartInfo(new Uri(new Uri(Url), relative).ToString()) { UseShellExecute = true });
    }
    public void Stop()
    {
        if (_process is null) return;
        try { if (!_process.HasExited) _process.Kill(true); } catch { }
        _process.Dispose(); _process = null; Url = null;
    }
    private static async Task DrainErrorsAsync(Process process)
    {
        while (!process.HasExited && await process.StandardError.ReadLineAsync() is { } line) Debug.WriteLine($"Trim web editor: {line}");
    }
    private static string FindPython(string root)
    {
        var venv=Path.Combine(root,".venv","Scripts","python.exe");if(File.Exists(venv))return venv;
        var bundled=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".cache","codex-runtimes","codex-primary-runtime","dependencies","python","python.exe");return File.Exists(bundled)?bundled:"python";
    }
    public void Dispose()=>Stop();
}
