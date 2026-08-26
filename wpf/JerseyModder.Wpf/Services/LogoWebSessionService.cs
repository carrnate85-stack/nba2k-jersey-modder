using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Nodes;

namespace JerseyModder.Wpf.Services;

public sealed class LogoWebSessionService : IDisposable
{
    private static readonly HttpClient Http = new();
    private readonly string _projectRoot;
    private Process? _process;

    public string? Url { get; private set; }
    public string? StatePath { get; private set; }

    public LogoWebSessionService(string projectRoot) => _projectRoot = projectRoot;

    public async Task<string> StartAsync(string referencePath, bool openBrowser = true, CancellationToken cancellationToken = default)
    {
        Stop();
        var sessionFolder = Path.Combine(
            Path.GetTempPath(), "nba2k_jersey_modder", "wpf_logo_web", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(sessionFolder);
        StatePath = Path.Combine(sessionFolder, "state.json");

        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = FindPython(_projectRoot),
                WorkingDirectory = _projectRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            },
        };
        process.StartInfo.ArgumentList.Add("-u");
        process.StartInfo.ArgumentList.Add(Path.Combine(_projectRoot, "tools", "wpf_logo_web.py"));
        process.StartInfo.ArgumentList.Add("--reference");
        process.StartInfo.ArgumentList.Add(referencePath);
        process.StartInfo.ArgumentList.Add("--state");
        process.StartInfo.ArgumentList.Add(StatePath);
        process.Start();
        _process = process;
        _ = DrainErrorsAsync(process);

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        var line = await process.StandardOutput.ReadLineAsync(timeout.Token)
            ?? throw new InvalidOperationException("The logo web editor did not start.");
        var startup = JsonNode.Parse(line)?.AsObject()
            ?? throw new InvalidDataException("The logo web editor returned invalid startup information.");
        Url = startup["url"]?.GetValue<string>()
            ?? throw new InvalidDataException("The logo web editor did not provide an address.");
        if (openBrowser) OpenBrowser();
        return Url;
    }

    public async Task ImportAsync(string sourcePath, string target, CancellationToken cancellationToken = default)
    {
        if (Url is null) await StartAsync(sourcePath, false, cancellationToken);
        using var response = await Http.PostAsJsonAsync(
            new Uri(new Uri(Url!), "api/import"),
            new { path = sourcePath, target },
            cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            var error = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new InvalidOperationException($"The logo could not be staged. {error}");
        }
    }

    public void OpenBrowser() => OpenPath(string.Empty);

    public void OpenEditor() => OpenPath("edit");

    private void OpenPath(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(Url))
            throw new InvalidOperationException("Upload a reference image first.");
        var destination = new Uri(new Uri(Url), relativePath).ToString();
        Process.Start(new ProcessStartInfo(destination) { UseShellExecute = true });
    }

    public void Stop()
    {
        if (_process is null) return;
        try
        {
            if (!_process.HasExited) _process.Kill(true);
        }
        catch { }
        _process.Dispose();
        _process = null;
        Url = null;
    }

    private static async Task DrainErrorsAsync(Process process)
    {
        while (!process.HasExited && await process.StandardError.ReadLineAsync() is { } line)
            Debug.WriteLine($"Logo web editor: {line}");
    }

    private static string FindPython(string root)
    {
        var venv = Path.Combine(root, ".venv", "Scripts", "python.exe");
        if (File.Exists(venv)) return venv;
        var bundled = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "python.exe");
        return File.Exists(bundled) ? bundled : "python";
    }

    public void Dispose() => Stop();
}
