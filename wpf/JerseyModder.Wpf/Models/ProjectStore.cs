using System.ComponentModel;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace JerseyModder.Wpf.Models;

public sealed class ProjectStore : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;
    public event EventHandler? Changed;

    public JsonObject Root { get; private set; }
    public string? FilePath { get; private set; }
    public bool IsDirty { get; private set; }

    public JsonObject Generator => Root["generator"]!.AsObject();
    public JsonObject Colors => Generator["colors"]!.AsObject();
    public JsonObject Images => Generator["images"]!.AsObject();

    public ProjectStore(JsonObject? root = null, string? filePath = null)
    {
        Root = Normalize(root ?? CreateDefaultRoot());
        FilePath = filePath;
    }

    public string Garment
    {
        get => GetString(Generator, "garment", "Jersey");
        set => Set(Generator, "garment", value);
    }

    public string TemplateName
    {
        get => Garment == "Shorts" ? GetString(Generator, "shortsTemplate", "Retro shorts") : GetString(Generator, "jerseyCut", "Retro U");
        set => Set(Generator, Garment == "Shorts" ? "shortsTemplate" : "jerseyCut", value);
    }

    public string GetColor(string key) => GetString(Colors, key, "");
    public void SetColor(string key, string value) => Set(Colors, key, value);
    public string? GetImage(string key) => Images[key]?.GetValue<string>();
    public void SetImage(string key, string? value) => Set(Images, key, value);

    public void Replace(JsonObject root, string? filePath = null)
    {
        Root = Normalize(root);
        FilePath = filePath;
        IsDirty = false;
        PropertyChanged?.Invoke(this, new(null));
        Changed?.Invoke(this, EventArgs.Empty);
    }

    public void ApplyExternal(JsonObject root)
    {
        Root = Normalize(root);
        IsDirty = true;
        PropertyChanged?.Invoke(this, new(null));
        Changed?.Invoke(this, EventArgs.Empty);
    }

    public void MarkClean()
    {
        IsDirty = false;
        PropertyChanged?.Invoke(this, new(nameof(IsDirty)));
    }

    public void MarkChanged()
    {
        IsDirty = true;
        PropertyChanged?.Invoke(this, new(nameof(IsDirty)));
        Changed?.Invoke(this, EventArgs.Empty);
    }

    public async Task SaveAsync(string? path = null)
    {
        var filePath = PrepareSave(path);
        await File.WriteAllTextAsync(filePath, Serialize());
        MarkClean();
    }

    public void Save(string? path = null)
    {
        var filePath = PrepareSave(path);
        File.WriteAllText(filePath, Serialize());
        MarkClean();
    }

    public static async Task<ProjectStore> LoadAsync(string path)
    {
        var text = await File.ReadAllTextAsync(path);
        return new ProjectStore(JsonNode.Parse(text)?.AsObject() ?? throw new InvalidDataException("Project JSON is invalid."), path);
    }

    public static ProjectStore Load(string path)
    {
        var text = File.ReadAllText(path);
        return new ProjectStore(JsonNode.Parse(text)?.AsObject() ?? throw new InvalidDataException("Project JSON is invalid."), path);
    }

    public JsonObject Snapshot() => JsonNode.Parse(Root.ToJsonString())!.AsObject();

    private string PrepareSave(string? path)
    {
        FilePath = path ?? FilePath ?? throw new InvalidOperationException("Choose a project file first.");
        Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
        return FilePath;
    }

    private string Serialize() => Root.ToJsonString(new JsonSerializerOptions { WriteIndented = true });

    private void Set(JsonObject target, string key, object? value)
    {
        var current = target[key]?.ToJsonString();
        target[key] = JsonValue.Create(value);
        if (current != target[key]?.ToJsonString()) MarkChanged();
    }

    private static string GetString(JsonObject target, string key, string fallback) => target[key]?.GetValue<string>() ?? fallback;

    private static JsonObject Normalize(JsonObject root)
    {
        var defaults = CreateDefaultRoot();
        Merge(root, defaults);
        root["projectVersion"] = 3;
        return root;
    }

    private static void Merge(JsonObject target, JsonObject defaults)
    {
        foreach (var pair in defaults)
        {
            if (target[pair.Key] is null) target[pair.Key] = pair.Value?.DeepClone();
            else if (target[pair.Key] is JsonObject child && pair.Value is JsonObject childDefaults) Merge(child, childDefaults);
        }
    }

    private static JsonObject CreateDefaultRoot() => JsonNode.Parse(File.ReadAllText(
        Path.Combine(JerseyModder.Wpf.Services.ProjectWorkspace.ApplicationRoot, "assets", "project-defaults.json")))!.AsObject();
}
