using System.IO;
using System.Text.Json.Nodes;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using JerseyModder.Wpf.Services;
using JerseyModder.Wpf.Models;
using Microsoft.Win32;

namespace JerseyModder.Wpf.Views;

public partial class GeneratorPage : ToolPageBase
{
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromMilliseconds(120) };
    private bool _loading;
    private int _revision;
    private readonly LayerWebSessionService _layerWeb;
    private readonly DispatcherTimer _layerStateTimer = new() { Interval = TimeSpan.FromMilliseconds(400) };
    private DateTime _lastLayerStateWrite;
    private bool _returnHandled;
    private ProjectStore? _subscribedProject;
    private static readonly (string Key, string Label, bool Jersey, bool Shorts)[] Colors =
    {
        ("front_color","Front base",true,false),("back_color","Back base",true,false),
        ("left_panel_color","Left side panel",true,false),("right_panel_color","Right side panel",true,false),
        ("collar_background_color","Collar background",true,false),("left_arm_hole_trim_color","Left arm hole trim",true,false),
        ("right_arm_hole_trim_color","Right arm hole trim",true,false),("collar_trim_color","Collar trim",true,false),
        ("waistband_color","Waistband",false,true)
    };
    private static readonly (string Key, string Label, bool Jersey, bool Shorts)[] Images =
    {
        ("front_wordmark_image","Front wordmark",true,false),("jersey_background_image","Background jersey image",true,false),
        ("left_panel_image","Left side panel",true,false),("right_panel_image","Right side panel",true,false),
        ("collar_trim_image","Collar trim",true,false),("left_arm_hole_trim_image","Left arm hole trim",true,false),
        ("right_arm_hole_trim_image","Right arm hole trim",true,false),("shorts_left_panel_image","Left shorts panel",false,true),
        ("shorts_right_panel_image","Right shorts panel",false,true),("waistband_image","Waistband image",false,true)
    };
    private readonly Dictionary<string, FrameworkElement> _colorRows = new();
    private readonly Dictionary<string, FrameworkElement> _imageRows = new();

    public GeneratorPage(WorkspaceContext context) : base(context)
    {
        InitializeComponent();
        _layerWeb = new LayerWebSessionService(context.ProjectRoot);
        _timer.Tick += (_, _) => { _timer.Stop(); _ = RenderAsync(); };
        _layerStateTimer.Tick += async (_, _) => await RefreshLayerStateAsync();
        _layerStateTimer.Start();
        Application.Current.Exit += (_, _) => _layerWeb.Dispose();
        BuildColorRows(); BuildImageRows(); LoadProject();
        SubscribeToProject();
    }

    private void BuildColorRows()
    {
        foreach (var item in Colors)
        {
            var row = new Grid { Margin = new Thickness(0, 0, 0, 7), Tag = item };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(145) }); row.ColumnDefinitions.Add(new ColumnDefinition()); row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var label = new TextBlock { Text = item.Label, VerticalAlignment = VerticalAlignment.Center };
            var box = new TextBox { Text = "#ffffff", Tag = item.Key, Margin = new Thickness(0, 0, 7, 0) }; box.TextChanged += OnColorTextChanged;
            var none = new CheckBox { Content = "No color", Tag = new object[] { item.Key, box }, VerticalAlignment = VerticalAlignment.Center }; none.Checked += OnNoColor; none.Unchecked += OnNoColor;
            Grid.SetColumn(box, 1); Grid.SetColumn(none, 2); row.Children.Add(label); row.Children.Add(box); row.Children.Add(none); ColorPanel.Children.Add(row); _colorRows[item.Key] = row;
        }
    }

    private void BuildImageRows()
    {
        foreach (var item in Images)
        {
            var row = new Grid { Margin = new Thickness(0, 0, 0, 7), Tag = item };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(145) }); row.ColumnDefinitions.Add(new ColumnDefinition()); row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var label = new TextBlock { Text = item.Label, VerticalAlignment = VerticalAlignment.Center };
            var path = new TextBlock { Tag = item.Key, Text = "None", Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"], TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0,0,7,0) };
            var choose = new Button { Content = "Choose", Tag = new object[] { item.Key, path }, Padding = new Thickness(8,4,8,4) }; choose.Click += OnChooseImage;
            var clear = new Button { Content = "Clear", Tag = new object[] { item.Key, path }, Padding = new Thickness(8,4,8,4), Margin = new Thickness(0) }; clear.Click += OnClearImage;
            Grid.SetColumn(path,1); Grid.SetColumn(choose,2); Grid.SetColumn(clear,3); row.Children.Add(label); row.Children.Add(path); row.Children.Add(choose); row.Children.Add(clear); ImagePanel.Children.Add(row); _imageRows[item.Key] = row;
        }
        var tile = new CheckBox { Name = "TileBackground", Content = "Tile background jersey image", Margin = new Thickness(145,4,0,4), IsChecked = Context.Project.Generator["jerseyBackground"]?["tile"]?.GetValue<bool>() ?? false };
        tile.Click += (_, _) => { Context.Project.Generator["jerseyBackground"]!["tile"] = tile.IsChecked == true; Context.Project.MarkChanged(); };
        ImagePanel.Children.Add(tile);
    }

    protected override void OnProjectReplaced() { _layerWeb.Stop(); _lastLayerStateWrite = default; SubscribeToProject(); LoadProject(); }
    private void SubscribeToProject()
    {
        if (ReferenceEquals(_subscribedProject, Context.Project)) return;
        if (_subscribedProject is not null) _subscribedProject.Changed -= OnProjectChanged;
        _subscribedProject = Context.Project;
        _subscribedProject.Changed += OnProjectChanged;
    }
    private void OnProjectChanged(object? sender, EventArgs e) { if (!_loading) Schedule(); }
    private void LoadProject()
    {
        _loading = true;
        foreach (var (key, _, _, _) in Colors)
        {
            if (_colorRows[key] is not Grid row) continue;
            var box = (TextBox)row.Children[1]; var none = (CheckBox)row.Children[2]; var value = Context.Project.GetColor(key);
            box.Text = string.IsNullOrEmpty(value) ? "#ffffff" : value; none.IsChecked = string.IsNullOrEmpty(value); box.IsEnabled = none.IsChecked != true;
        }
        foreach (var (key, _, _, _) in Images)
        {
            if (_imageRows[key] is Grid row && row.Children[1] is TextBlock path) path.Text = Path.GetFileName(Context.Project.GetImage(key)) ?? "None";
        }
        var uv = Context.Project.Generator["uvOverlay"]!.AsObject(); UvEnabled.IsChecked = uv["enabled"]?.GetValue<bool>() ?? true; UvOpacity.Value = uv["opacity"]?.GetValue<int>() ?? 45;
        var number = Context.Project.Generator["numberPreview"]!.AsObject(); NumberEnabled.IsChecked = number["enabled"]?.GetValue<bool>() ?? true; NumberText.Text = number["text"]?.GetValue<string>() ?? "15";
        RefreshGarmentVisibility(); RefreshLists(); _loading = false; Schedule();
    }

    private void RefreshGarmentVisibility()
    {
        var shorts = Context.Project.Garment == "Shorts";
        foreach (var row in _colorRows.Values) { var item = ((string Key,string Label,bool Jersey,bool Shorts))row.Tag; row.Visibility = (shorts ? item.Shorts : item.Jersey) ? Visibility.Visible : Visibility.Collapsed; }
        foreach (var row in _imageRows.Values) { var item = ((string Key,string Label,bool Jersey,bool Shorts))row.Tag; row.Visibility = (shorts ? item.Shorts : item.Jersey) ? Visibility.Visible : Visibility.Collapsed; }
        WaistbandSection.Visibility = shorts ? Visibility.Visible : Visibility.Collapsed;
    }

    private void RefreshLists()
    {
        TrimPathSummary.Text = $"{(Context.Project.Generator["trimPathLayers"] as JsonArray)?.Count ?? 0} path layer(s) for this project";
    }

    private void OnColorTextChanged(object sender, TextChangedEventArgs e)
    {
        if (_loading || sender is not TextBox { Tag: string key } box || box.Text.Length != 7 || !box.Text.StartsWith('#')) return;
        Context.Project.SetColor(key, box.Text);
    }
    private void OnNoColor(object sender, RoutedEventArgs e)
    {
        if (_loading || sender is not CheckBox check || check.Tag is not object[] data) return;
        var key = (string)data[0]; var box = (TextBox)data[1]; box.IsEnabled = check.IsChecked != true; Context.Project.SetColor(key, check.IsChecked == true ? "" : box.Text);
    }
    private void OnChooseImage(object sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: object[] data }) return;
        var dialog = new OpenFileDialog { Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.dds|All files|*.*" };
        if (dialog.ShowDialog() != true) return; Context.Project.SetImage((string)data[0], dialog.FileName); ((TextBlock)data[1]).Text = Path.GetFileName(dialog.FileName);
    }
    private void OnClearImage(object sender, RoutedEventArgs e) { if (sender is Button { Tag: object[] data }) { Context.Project.SetImage((string)data[0], null); ((TextBlock)data[1]).Text = "None"; } }
    private void OnUvChanged(object sender, RoutedEventArgs e)
    {
        UvValue.Text = $"{UvOpacity.Value:0}%"; if (_loading) return; var uv = Context.Project.Generator["uvOverlay"]!.AsObject(); uv["enabled"] = UvEnabled.IsChecked == true; uv["opacity"] = (int)UvOpacity.Value; Context.Project.MarkChanged();
    }
    private void OnNumberChanged(object sender, RoutedEventArgs e)
    {
        if (_loading) return; var number = Context.Project.Generator["numberPreview"]!.AsObject(); number["enabled"] = NumberEnabled.IsChecked == true; number["text"] = NumberText.Text; Context.Project.MarkChanged();
    }
    private void OnGenerate(object sender, RoutedEventArgs e) => _ = RenderAsync();
    private void OnFit(object sender, RoutedEventArgs e) => Preview.Fit();
    private void OnLayerEditor(object sender, RoutedEventArgs e) => OpenWebLayerEditor();
    public async void OpenWebLayerEditor()
    {
        try
        {
            if (_layerWeb.Url is not null) { _layerWeb.OpenBrowser(); return; }
            Status("Opening web layer editor...");
            await _layerWeb.StartAsync(Context.Project.Snapshot());
            _lastLayerStateWrite = _layerWeb.StatePath is not null && File.Exists(_layerWeb.StatePath)
                ? File.GetLastWriteTimeUtc(_layerWeb.StatePath) : default;
            _returnHandled = false;
            Status("Web layer editor opened. Changes will update this preview automatically.");
        }
        catch (Exception ex) { Error("Web Layer Editor", ex); }
    }

    private async Task RefreshLayerStateAsync()
    {
        var path = _layerWeb.StatePath;
        if (path is null || !File.Exists(path)) return;
        var write = File.GetLastWriteTimeUtc(path);
        if (write <= _lastLayerStateWrite) return;
        try
        {
            var root = JsonNode.Parse(await File.ReadAllTextAsync(path))?.AsObject();
            var project = root?["project"]?.AsObject();
            if (project is null) return;
            _lastLayerStateWrite = write;
            if (project.ToJsonString() != Context.Project.Snapshot().ToJsonString())
                Context.Project.ApplyExternal((JsonObject)project.DeepClone());
            if (root?["returnRequested"]?.GetValue<bool>() == true && !_returnHandled)
            {
                _returnHandled = true;
                var window = Window.GetWindow(this) ?? Application.Current.MainWindow;
                if (window is not null)
                {
                    if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
                    window.Show(); window.Activate(); window.Topmost = true; window.Topmost = false; window.Focus();
                }
                Status("Returned from the web layer editor.");
            }
        }
        catch (IOException) { }
        catch (JsonException) { }
    }
    private void OnOpenPaths(object sender, RoutedEventArgs e) => Status("Select Trim Path Lab in the left navigation.");
    private void Schedule() { RefreshGarmentVisibility(); _timer.Stop(); _timer.Start(); }

    private async Task RenderAsync()
    {
        var revision = ++_revision; PreviewStatus.Text = "Rendering 2048 x 2048 preview...";
        try
        {
            var result = (await Context.Bridge.CallAsync("render", new { project = Context.Project.Snapshot(), kind = "preview" }))!.AsObject();
            if (revision != _revision) return; Preview.Load(result["path"]?.GetValue<string>()); PreviewStatus.Text = $"{Context.Project.Garment} | {Context.Project.TemplateName} | 2048 x 2048";
        }
        catch (Exception ex) { if (revision == _revision) PreviewStatus.Text = ex.Message; }
    }
}
