using System.Diagnostics;
using System.IO;
using System.Text.Json.Nodes;

namespace JerseyModder.Wpf.Services;

public sealed class LayerWebSessionService : IDisposable
{
    private readonly string _projectRoot;
    private Process? _process;
    public string? Url { get; private set; }
    public string? StatePath { get; private set; }

    public LayerWebSessionService(string projectRoot) => _projectRoot = projectRoot;

    public async Task<string> StartAsync(JsonObject project, CancellationToken cancellationToken = default)
    {
        Stop();
        var folder = Path.Combine(Path.GetTempPath(), "nba2k_jersey_modder", "wpf_layer_web", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var projectPath = Path.Combine(folder, "project.json");
        StatePath = Path.Combine(folder, "state.json");
        await File.WriteAllTextAsync(projectPath, project.ToJsonString(), cancellationToken);

        var process = new Process { StartInfo = new ProcessStartInfo
        {
            FileName = FindPython(_projectRoot), WorkingDirectory = _projectRoot,
            UseShellExecute = false, RedirectStandardOutput = true,
            RedirectStandardError = true, CreateNoWindow = true,
        }};
        process.StartInfo.ArgumentList.Add("-u");
        process.StartInfo.ArgumentList.Add(Path.Combine(_projectRoot, "tools", "wpf_layer_web.py"));
        process.StartInfo.ArgumentList.Add("--project"); process.StartInfo.ArgumentList.Add(projectPath);
        process.StartInfo.ArgumentList.Add("--state"); process.StartInfo.ArgumentList.Add(StatePath);
        process.Start(); _process = process; _ = DrainErrorsAsync(process);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(20));
        var line = await process.StandardOutput.ReadLineAsync(timeout.Token)
            ?? throw new InvalidOperationException("The web layer editor did not start.");
        Url = JsonNode.Parse(line)?["url"]?.GetValue<string>()
            ?? throw new InvalidDataException("The web layer editor returned an invalid address.");
        OpenBrowser();
        return Url;
    }

    public void OpenBrowser()
    {
        if (string.IsNullOrWhiteSpace(Url)) throw new InvalidOperationException("Open the web layer editor first.");
        Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
    }

    public void Stop()
    {
        if (_process is null) return;
        try { if (!_process.HasExited) _process.Kill(true); } catch { }
        _process.Dispose(); _process = null; Url = null; StatePath = null;
    }

    private static async Task DrainErrorsAsync(Process process)
    {
        while (!process.HasExited && await process.StandardError.ReadLineAsync() is { } line)
            Debug.WriteLine($"Layer web editor: {line}");
    }

    private static string FindPython(string root)
    {
        var venv = Path.Combine(root, ".venv", "Scripts", "python.exe"); if (File.Exists(venv)) return venv;
        var bundled = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "python.exe");
        return File.Exists(bundled) ? bundled : "python";
    }

    public void Dispose() => Stop();
}
