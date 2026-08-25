using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace JerseyModder.Wpf.Services;

public sealed class PythonBridge : IAsyncDisposable
{
    private readonly string _projectRoot;
    private readonly Process _process;
    private readonly ConcurrentDictionary<long, TaskCompletionSource<JsonNode?>> _pending = new();
    private long _nextId;

    public PythonBridge(string projectRoot)
    {
        _projectRoot = projectRoot;
        var python = FindPython(projectRoot);
        var engine = Path.Combine(projectRoot, "tools", "wpf_engine.py");
        _process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = $"-u \"{engine}\"",
                WorkingDirectory = projectRoot,
                UseShellExecute = false,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            },
            EnableRaisingEvents = true,
        };
        _process.Start();
        _ = ReadLoopAsync();
        _ = ReadErrorsAsync();
    }

    public async Task<JsonNode?> CallAsync(string method, object? parameters = null, CancellationToken cancellationToken = default)
    {
        var id = Interlocked.Increment(ref _nextId);
        var source = new TaskCompletionSource<JsonNode?>(TaskCreationOptions.RunContinuationsAsynchronously);
        _pending[id] = source;
        var request = new JsonObject
        {
            ["id"] = id,
            ["method"] = method,
            ["params"] = parameters is null ? new JsonObject() : JsonSerializer.SerializeToNode(parameters),
        };
        await _process.StandardInput.WriteLineAsync(request.ToJsonString());
        await _process.StandardInput.FlushAsync();
        using var registration = cancellationToken.Register(() => source.TrySetCanceled(cancellationToken));
        return await source.Task;
    }

    private async Task ReadLoopAsync()
    {
        while (!_process.HasExited && await _process.StandardOutput.ReadLineAsync() is { } line)
        {
            try
            {
                var response = JsonNode.Parse(line)!.AsObject();
                var id = response["id"]!.GetValue<long>();
                if (!_pending.TryRemove(id, out var source)) continue;
                if (response["ok"]?.GetValue<bool>() == true) source.TrySetResult(response["result"]?.DeepClone());
                else source.TrySetException(new InvalidOperationException(response["error"]?.GetValue<string>() ?? "Python engine failed."));
            }
            catch { }
        }
        foreach (var source in _pending.Values) source.TrySetException(new IOException("Python engine stopped."));
        _pending.Clear();
    }

    private async Task ReadErrorsAsync()
    {
        while (!_process.HasExited && await _process.StandardError.ReadLineAsync() is { } line)
            Debug.WriteLine($"Python engine: {line}");
    }

    private static string FindPython(string root)
    {
        var venv = Path.Combine(root, ".venv", "Scripts", "python.exe");
        if (File.Exists(venv)) return venv;
        var bundled = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "python.exe");
        if (File.Exists(bundled)) return bundled;
        return "python";
    }

    public async ValueTask DisposeAsync()
    {
        try { await _process.StandardInput.WriteLineAsync("{\"id\":0,\"method\":\"shutdown\",\"params\":{}}"); }
        catch { }
        if (!_process.WaitForExit(1500)) _process.Kill(true);
        _process.Dispose();
    }
}
