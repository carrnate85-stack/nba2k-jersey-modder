using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;
using JerseyModder.Wpf.Services;

namespace JerseyModder.Wpf.Views;

public partial class LayerEditorWindow : Window
{
    private readonly WorkspaceContext _context;
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromMilliseconds(100) };
    private bool _loading;
    private int _revision;
    private sealed record LayerItem(string Name, string Kind, int Index, string Key);

    public LayerEditorWindow(WorkspaceContext context)
    {
        InitializeComponent(); _context = context; _timer.Tick += (_, _) => { _timer.Stop(); _ = RenderAsync(); };
        LoadProject(); Loaded += (_, _) => _ = RenderAsync();
    }

    private void LoadProject()
    {
        _loading = true; var items = new List<LayerItem>(); var g = _context.Project.Generator;
        var logos = g["logos"] as JsonArray; if (logos is not null) for (var i = logos.Count - 1; i >= 0; i--) items.Add(new($"Logo: {Path.GetFileName(logos[i]?["path"]?.GetValue<string>())}", "logo", i, $"logo:{i}"));
        var paths = g["trimPathLayers"] as JsonArray; if (paths is not null) for (var i = paths.Count - 1; i >= 0; i--) items.Add(new($"Trim path: {paths[i]?["name"]?.GetValue<string>()}", "path", i, $"path:{i}"));
        var imageKeys = _context.Project.Garment == "Shorts" ? new[] { ("shorts_left_panel_image","shorts_left_panel"),("shorts_right_panel_image","shorts_right_panel"),("waistband_image","shorts_waistband") } : new[] { ("front_wordmark_image","frontWordmark"),("left_panel_image","left_side_panel"),("right_panel_image","right_side_panel"),("collar_trim_image","collar_trim"),("left_arm_hole_trim_image","left_arm_hole_trim"),("right_arm_hole_trim_image","right_arm_hole_trim") };
        foreach (var (key, zone) in imageKeys) if (!string.IsNullOrWhiteSpace(_context.Project.GetImage(key))) items.Add(new($"Image: {Path.GetFileName(_context.Project.GetImage(key))}", zone == "frontWordmark" ? "wordmark" : "image", -1, zone));
        LayerList.ItemsSource = items; UvEnabled.IsChecked = g["uvOverlay"]?["enabled"]?.GetValue<bool>() ?? true; UvOpacity.Value = g["uvOverlay"]?["opacity"]?.GetValue<int>() ?? 45; _loading = false;
        if (items.Count > 0) LayerList.SelectedIndex = 0;
    }

    private JsonObject? SelectedData()
    {
        if (LayerList.SelectedItem is not LayerItem item) return null; var g = _context.Project.Generator;
        if (item.Kind == "logo") return g["logos"]?[item.Index]?.AsObject();
        if (item.Kind == "path") return g["trimPathLayers"]?[item.Index]?.AsObject();
        if (item.Kind == "wordmark") return g["frontWordmark"]!.AsObject();
        var placements = g["trimPlacements"]!.AsObject(); if (placements[item.Key] is not JsonObject value) placements[item.Key] = value = new JsonObject(); return value;
    }

    private void OnLayerSelected(object sender, SelectionChangedEventArgs e)
    {
        var item = LayerList.SelectedItem as LayerItem; var data = SelectedData(); if (item is null || data is null) return;
        _loading = true;
        if (item.Kind == "path") { XValue.Text = Value(data,"x",0); YValue.Text = Value(data,"y",0); WidthValue.Text = Value(data,"width",2048); HeightValue.Text = Value(data,"height",2048); RotationValue.Text = Value(data,"rotationDegrees",0); }
        else { XValue.Text = Value(data,"offsetX",0); YValue.Text = Value(data,"offsetY",0); WidthValue.Text = Value(data,"scaleWidthPercent",100); HeightValue.Text = Value(data,"scaleHeightPercent",100); RotationValue.Text = Value(data,"rotationDegrees",0); }
        var cleanup = _context.Project.Generator["webEditor"]!["layerCleanup"]!.AsObject()[item.Key] as JsonObject;
        AutoBackground.IsChecked = cleanup?["autoBackground"]?.GetValue<bool>() ?? false; RemoveWhite.IsChecked = cleanup?["removeWhite"]?.GetValue<bool>() ?? false; RemoveBlack.IsChecked = cleanup?["removeBlack"]?.GetValue<bool>() ?? false; OutsideOnly.IsChecked = cleanup?["outsideOnly"]?.GetValue<bool>() ?? true;
        _loading = false;
    }
    private static string Value(JsonObject data, string key, double fallback) => (data[key]?.GetValue<double>() ?? fallback).ToString("0.##");

    private void OnTransform(object sender, RoutedEventArgs e) => ApplyTransform();
    private void ApplyTransform()
    {
        if (_loading || LayerList.SelectedItem is not LayerItem item || SelectedData() is not JsonObject data) return;
        if (!double.TryParse(XValue.Text, out var x) || !double.TryParse(YValue.Text, out var y) || !double.TryParse(WidthValue.Text, out var width) || !double.TryParse(HeightValue.Text, out var height) || !double.TryParse(RotationValue.Text, out var rotation)) return;
        if (item.Kind == "path") { data["x"] = (int)x; data["y"] = (int)y; data["width"] = Math.Max(1,(int)width); data["height"] = Math.Max(1,(int)height); }
        else { data["offsetX"] = (int)x; data["offsetY"] = (int)y; data["scaleWidthPercent"] = Math.Clamp((int)width,1,500); data["scaleHeightPercent"] = Math.Clamp((int)height,1,500); }
        data["rotationDegrees"] = rotation; _context.Project.MarkChanged(); Schedule();
    }

    private void OnKeyDown(object sender, KeyEventArgs e)
    {
        if (LayerList.SelectedItem is null || e.OriginalSource is TextBox) return; var step = Keyboard.Modifiers.HasFlag(ModifierKeys.Shift) ? 10 : 1;
        var dx = e.Key == Key.Left ? -step : e.Key == Key.Right ? step : 0; var dy = e.Key == Key.Up ? -step : e.Key == Key.Down ? step : 0; if (dx == 0 && dy == 0) return;
        XValue.Text = (double.Parse(XValue.Text) + dx).ToString(); YValue.Text = (double.Parse(YValue.Text) + dy).ToString(); ApplyTransform(); e.Handled = true;
    }

    private void OnUv(object sender, RoutedEventArgs e)
    {
        UvText.Text = $"{UvOpacity.Value:0}%"; if (_loading) return; var uv = _context.Project.Generator["uvOverlay"]!.AsObject(); uv["enabled"] = UvEnabled.IsChecked == true; uv["opacity"] = (int)UvOpacity.Value; _context.Project.MarkChanged(); Schedule();
    }
    private void OnCleanup(object sender, RoutedEventArgs e)
    {
        if (LayerList.SelectedItem is not LayerItem item) return; var cleanup = _context.Project.Generator["webEditor"]!["layerCleanup"]!.AsObject(); cleanup[item.Key] = new JsonObject { ["autoBackground"] = AutoBackground.IsChecked == true, ["removeWhite"] = RemoveWhite.IsChecked == true, ["removeBlack"] = RemoveBlack.IsChecked == true, ["outsideOnly"] = OutsideOnly.IsChecked == true, ["tolerance"] = 32 }; _context.Project.MarkChanged(); Schedule();
    }
    private void OnReset(object sender, RoutedEventArgs e) { XValue.Text="0";YValue.Text="0";WidthValue.Text="100";HeightValue.Text="100";RotationValue.Text="0";ApplyTransform(); }
    private void OnRefresh(object sender, RoutedEventArgs e) => _ = RenderAsync();
    private void OnDone(object sender, RoutedEventArgs e) => Close();
    private void Schedule() { _timer.Stop(); _timer.Start(); }
    private async Task RenderAsync()
    {
        var revision=++_revision; try { var result=(await _context.Bridge.CallAsync("render",new {project=_context.Project.Snapshot(),kind="preview"}))!.AsObject(); if(revision==_revision) Preview.Load(result["path"]?.GetValue<string>()); } catch(Exception ex) { _context.SetStatus(ex.Message); }
    }
}
