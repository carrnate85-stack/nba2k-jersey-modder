using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using JerseyModder.Wpf.Services;
using Microsoft.Win32;

namespace JerseyModder.Wpf.Views;

public partial class GeneratorPage : ToolPageBase
{
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromMilliseconds(120) };
    private bool _loading;
    private int _revision;
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
        _timer.Tick += (_, _) => { _timer.Stop(); _ = RenderAsync(); };
        foreach (var item in new[] { "Center Chest Logo", "Left Chest Logo", "Right Chest Logo", "Front Wordmark", "Wrap Logo", "Back Neck Logo", "Back Center Logo", "Belt Buckle Logo" }) LogoType.Items.Add(item);
        LogoType.SelectedIndex = 0;
        BuildColorRows(); BuildImageRows(); LoadProject();
        Context.Project.Changed += (_, _) => { if (!_loading) Schedule(); };
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

    protected override void OnProjectReplaced() => LoadProject();
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
        LogoList.ItemsSource = (Context.Project.Generator["logos"] as JsonArray)?.Select((node, index) => new { index, label = $"{node?["targetName"]}: {Path.GetFileName(node?["path"]?.GetValue<string>())}" }).ToList();
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
    private void OnAddLogo(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog { Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp|All files|*.*" }; if (dialog.ShowDialog() != true) return;
        var targets = new[] { "front_center_chest_logo","front_left_chest_logo","front_right_chest_logo","front_wordmark","wrap_across_front_back_logo","back_neck_logo","back_center_logo","shorts_belt_buckle_logo" };
        var target = targets[Math.Max(0, LogoType.SelectedIndex)];
        ((JsonArray)Context.Project.Generator["logos"]!).Add(new JsonObject { ["path"] = dialog.FileName, ["targetName"] = target, ["offsetX"] = 0, ["offsetY"] = 0, ["scalePercent"] = 100, ["scaleWidthPercent"] = 100, ["scaleHeightPercent"] = 100, ["rotation"] = 0 }); Context.Project.MarkChanged(); RefreshLists();
    }
    private void OnRemoveLogo(object sender, RoutedEventArgs e) { if (LogoList.SelectedIndex >= 0) { ((JsonArray)Context.Project.Generator["logos"]!).RemoveAt(LogoList.SelectedIndex); Context.Project.MarkChanged(); RefreshLists(); } }
    private void OnGenerate(object sender, RoutedEventArgs e) => _ = RenderAsync();
    private void OnFit(object sender, RoutedEventArgs e) => Preview.Fit();
    private void OnLayerEditor(object sender, RoutedEventArgs e) => new LayerEditorWindow(Context) { Owner = Window.GetWindow(this) }.Show();
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
