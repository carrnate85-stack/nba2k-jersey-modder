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
        FilePath = path ?? FilePath ?? throw new InvalidOperationException("Choose a project file first.");
        Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
        await File.WriteAllTextAsync(FilePath, Root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        MarkClean();
    }

    public static async Task<ProjectStore> LoadAsync(string path)
    {
        var text = await File.ReadAllTextAsync(path);
        return new ProjectStore(JsonNode.Parse(text)?.AsObject() ?? throw new InvalidDataException("Project JSON is invalid."), path);
    }

    public JsonObject Snapshot() => JsonNode.Parse(Root.ToJsonString())!.AsObject();

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

    private static JsonObject CreateDefaultRoot() => JsonNode.Parse("""
    {
      "app":"NBA 2K Jersey Modder","projectVersion":3,
      "generator":{
        "garment":"Jersey","jerseyCut":"Retro U","shortsTemplate":"Retro shorts",
        "colors":{"front_color":"#ffffff","back_color":"#ffffff","left_panel_color":"","right_panel_color":"","collar_background_color":"#ffffff","waistband_color":"#ffffff","left_arm_hole_trim_color":"#ffffff","right_arm_hole_trim_color":"#ffffff","collar_trim_color":"#ffffff"},
        "images":{"left_panel_image":null,"right_panel_image":null,"shorts_left_panel_image":null,"shorts_right_panel_image":null,"waistband_image":null,"jersey_background_image":null,"front_wordmark_image":null,"left_arm_hole_trim_image":null,"right_arm_hole_trim_image":null,"collar_trim_image":null},
        "frontWordmark":{"offsetX":0,"offsetY":0,"scalePercent":100,"scaleWidthPercent":100,"scaleHeightPercent":100},
        "jerseyBackground":{"tile":false,"tileScalePercent":100},"logos":[],"trimPathLayers":[],"trimPlacements":{},
        "backgroundCleanup":{"removeWhite":false,"removeBlack":false,"outsideOnly":true,"tolerance":32},
        "fabricOverlay":{"preset":"None","customPath":null,"blendMode":"multiply","opacity":0},
        "uvOverlay":{"enabled":true,"opacity":45},
        "numberPreview":{"enabled":true,"text":"15","x":1160,"y":780,"scale":100,"scaleWidth":100,"scaleHeight":100},
        "webEditor":{"layerOrder":[],"layerCleanup":{}}
      }
    }
    """)!.AsObject();
}
