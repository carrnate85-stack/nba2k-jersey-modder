using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Threading;
using JerseyModder.Wpf.Controls;
using JerseyModder.Wpf.Services;
using Microsoft.Win32;

namespace JerseyModder.Wpf.Views;

public sealed class LogoCreatorPage : ToolPageBase
{
    public sealed record StagedLogo(
        string Id, string Path, string ThumbnailPath, string Target, string TypeLabel)
    {
        public string FileName => System.IO.Path.GetFileName(Path);
        public override string ToString() => $"{TypeLabel}  |  {System.IO.Path.GetFileName(Path)}";
    }

    private readonly ImageViewport _reference = new(), _preview = new();
    private readonly TextBlock _sourceLabel = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        Text = "No reference loaded.",
        TextWrapping = TextWrapping.Wrap,
    };
    private readonly TextBlock _stageSummary = new()
    {
        Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"],
        Text = "Selections made in the browser will appear here.",
        Margin = new Thickness(0, 7, 0, 0),
    };
    private readonly ListBox _stagedList = new();
    private readonly Button _reopenButton;
    private readonly LogoWebSessionService _webSession;
    private readonly DispatcherTimer _stateTimer;
    private List<StagedLogo> _staged = [];
    private string? _source;
    private long _lastStateWrite;
    private bool _readingState;
    private bool _returnHandled;

    public LogoCreatorPage(WorkspaceContext context) : base(context)
    {
        _webSession = new LogoWebSessionService(context.ProjectRoot);
        _stateTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
        _stateTimer.Tick += async (_, _) => await RefreshStateAsync();
        _stateTimer.Start();
        Application.Current.Exit += (_, _) => _webSession.Dispose();

        var body = new Grid();
        body.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        body.RowDefinitions.Add(new RowDefinition());
        var commandBar = new Grid { Margin = new Thickness(0, 0, 0, 12) };
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        commandBar.ColumnDefinitions.Add(new ColumnDefinition());
        var upload = Ui.Button("Upload Reference and Open Web Logo Creator", OnOpen, true);
        upload.Margin = new Thickness(0, 0, 5, 0);
        _reopenButton = Ui.Button("Reopen Web Logo Creator", (_, _) => ReopenWebEditor(), true);
        _reopenButton.Margin = new Thickness(5, 0, 0, 0);
        _reopenButton.IsEnabled = false;
        commandBar.Children.Add(upload);
        Grid.SetColumn(_reopenButton, 1);
        commandBar.Children.Add(_reopenButton);
        body.Children.Add(commandBar);

        var left = new StackPanel();
        _reference.Height = 175;
        left.Children.Add(new GroupBox { Header = "Reference", Content = _reference });
        _sourceLabel.Margin = new Thickness(2, 7, 2, 12);
        left.Children.Add(_sourceLabel);
        _preview.Height = 225;
        left.Children.Add(new GroupBox { Header = "Selected Logo", Content = _preview });
        left.Children.Add(Ui.Button("Open Web Logo Creator", (_, _) => ReopenWebEditor(), true));

        var right = new Grid();
        right.RowDefinitions.Add(new RowDefinition());
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        _stagedList.ItemTemplate = BuildStageTemplate();
        _stagedList.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        _stagedList.SelectionChanged += async (_, _) => await ShowSelectedPreviewAsync();
        var stagedGroup = new GroupBox
        {
            Header = "Staged Logos",
            Content = _stagedList,
        };
        right.Children.Add(stagedGroup);
        Grid.SetRow(_stageSummary, 1);
        right.Children.Add(_stageSummary);
        var stageButtons = new Grid { Margin = new Thickness(0, 8, 0, 0) };
        stageButtons.ColumnDefinitions.Add(new ColumnDefinition());
        stageButtons.ColumnDefinitions.Add(new ColumnDefinition());
        stageButtons.ColumnDefinitions.Add(new ColumnDefinition());
        var edit = Ui.Button("Edit Staged Logos", (_, _) => OpenLogoEditor());
        var exportAi = Ui.Button("Export ChatGPT Logo Pack", ExportAiLogoPack);
        var send = Ui.Button("Send All to Generator", OnSend, true);
        edit.Margin = new Thickness(0, 0, 4, 0);
        exportAi.Margin = new Thickness(4, 0, 4, 0);
        send.Margin = new Thickness(4, 0, 0, 0);
        stageButtons.Children.Add(edit);
        Grid.SetColumn(exportAi, 1);
        stageButtons.Children.Add(exportAi);
        Grid.SetColumn(send, 2);
        stageButtons.Children.Add(send);
        Grid.SetRow(stageButtons, 2);
        right.Children.Add(stageButtons);

        var split = new Grid();
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(300) });
        split.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(12) });
        split.ColumnDefinitions.Add(new ColumnDefinition());
        var leftScroll = new ScrollViewer
        {
            Content = left,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        split.Children.Add(leftScroll);
        Grid.SetColumn(right, 2);
        split.Children.Add(right);
        Grid.SetRow(split, 1);
        body.Children.Add(split);
        Content = Ui.Page(
            "Logo Creator",
            "Load one reference, select several logos in the browser, then review and send the staged set to the Generator.",
            body);
    }

    private static DataTemplate BuildStageTemplate() => (DataTemplate)XamlReader.Parse("""
        <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
          <Grid Margin="4" Height="64">
            <Grid.ColumnDefinitions>
              <ColumnDefinition Width="84" />
              <ColumnDefinition Width="*" />
            </Grid.ColumnDefinitions>
            <Border Background="#EEF1F4" BorderBrush="#CBD2DB" BorderThickness="1" CornerRadius="3" Padding="3">
              <Image Source="{Binding ThumbnailPath}" Stretch="Uniform" />
            </Border>
            <StackPanel Grid.Column="1" Margin="10,0,0,0" VerticalAlignment="Center">
              <TextBlock Text="{Binding TypeLabel}" FontWeight="SemiBold" FontSize="14" />
              <TextBlock Text="{Binding FileName}" Foreground="#667180" Margin="0,4,0,0" TextTrimming="CharacterEllipsis" />
            </StackPanel>
          </Grid>
        </DataTemplate>
        """);

    private async void OnOpen(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose a logo reference image",
            Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif|All files|*.*",
        };
        if (dialog.ShowDialog() != true) return;
        _source = dialog.FileName;
        _sourceLabel.Text = $"Loading {Path.GetFileName(_source)}...";
        _staged = [];
        RefreshStagedList();
        try
        {
            var thumbnail = (await Context.Bridge.CallAsync("image_thumbnail", new
            {
                path = _source,
                maximumWidth = 1200,
                maximumHeight = 900,
            }))!.AsObject();
            _reference.Load(thumbnail["path"]?.GetValue<string>());
            _sourceLabel.Text = $"Reference: {Path.GetFileName(_source)}  |  " +
                $"{thumbnail["sourceWidth"]} x {thumbnail["sourceHeight"]}";
            Status("Starting web Logo Creator...");
            await _webSession.StartAsync(_source);
            _lastStateWrite = 0;
            _returnHandled = false;
            _reopenButton.IsEnabled = true;
            await RefreshStateAsync(true);
            Status("Web Logo Creator opened. Stage as many logos as you need from this reference.");
        }
        catch (Exception ex)
        {
            Error("Logo Creator", ex);
            _sourceLabel.Text = $"Could not open {Path.GetFileName(_source)}.";
        }
    }

    private void ReopenWebEditor()
    {
        try { _webSession.OpenBrowser(); }
        catch (Exception ex) { Error("Logo Creator", ex); }
    }

    private void OpenLogoEditor()
    {
        try { _webSession.OpenEditor(); }
        catch (Exception ex) { Error("Logo Editor", ex); }
    }

    private void ExportAiLogoPack(object sender, RoutedEventArgs e)
    {
        if (_staged.Count == 0)
        {
            MessageBox.Show("Stage one or more logos before exporting a ChatGPT pack.", "Logo Creator");
            return;
        }
        var dialog = new OpenFolderDialog
        {
            Title = "Choose where to create the ChatGPT logo pack",
            Multiselect = false,
        };
        if (dialog.ShowDialog() != true) return;
        try
        {
            var folder = NextPackFolder(dialog.FolderName);
            Directory.CreateDirectory(folder);
            var references = new List<string>();
            for (var index = 0; index < _staged.Count; index++)
            {
                var item = _staged[index];
                var name = $"{index + 1:00}_{SafeFileName(item.TypeLabel)}_reference.png";
                File.Copy(item.Path, Path.Combine(folder, name), true);
                references.Add($"{name}: {item.TypeLabel}");
            }
            File.WriteAllText(
                Path.Combine(folder, "chatgpt_logo_prompt.txt"),
                BuildAiLogoPrompt(references));
            Status($"Exported {_staged.Count} staged logo(s) to {folder}.");
            MessageBox.Show(
                $"Created a ChatGPT logo pack with {_staged.Count} reference image(s).\n\n{folder}",
                "Logo Pack Exported",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
        }
        catch (Exception ex) { Error("Export ChatGPT Logo Pack", ex); }
    }

    private static string NextPackFolder(string parent)
    {
        var basePath = Path.Combine(parent, "chatgpt_logo_pack");
        if (!Directory.Exists(basePath)) return basePath;
        for (var index = 2; ; index++)
        {
            var candidate = $"{basePath}_{index}";
            if (!Directory.Exists(candidate)) return candidate;
        }
    }

    private static string SafeFileName(string value)
    {
        var invalid = Path.GetInvalidFileNameChars();
        return new string(value.ToLowerInvariant().Select(character =>
            invalid.Contains(character) ? '_' : character == ' ' ? '_' : character).ToArray());
    }

    private static string BuildAiLogoPrompt(IEnumerable<string> references) => $"""
        Recreate every attached basketball uniform logo as a separate, polished, high-resolution PNG.

        Requirements:
        - Preserve the exact wording, design, colors, proportions, outline thickness, and intentional style of each reference.
        - Straighten photographed perspective, fabric curvature, accidental skew, uneven baselines, and wavy edges.
        - Preserve intentional arches, italics, curves, and asymmetry that belong to the original design.
        - Remove the jersey, background, wrinkles, compression artifacts, blur, and jagged edges.
        - Use a true transparent background with an alpha channel. Do not add white, black, gray, or checkerboard backgrounds.
        - Center each finished logo on a 2048 x 2048 transparent canvas with approximately 6 percent transparent padding.
        - Return one finished PNG for each reference, in the same numbered order.
        - Do not redesign the logos, change the text, add effects, or place them on a mockup.

        Reference order and intended logo types:
        {string.Join(Environment.NewLine, references)}
        """;

    private async Task RefreshStateAsync(bool force = false)
    {
        if (_readingState || string.IsNullOrWhiteSpace(_webSession.StatePath) ||
            !File.Exists(_webSession.StatePath)) return;
        var write = File.GetLastWriteTimeUtc(_webSession.StatePath).Ticks;
        if (!force && write == _lastStateWrite) return;
        _readingState = true;
        try
        {
            var root = JsonNode.Parse(await File.ReadAllTextAsync(_webSession.StatePath))?.AsObject();
            if (root is null) return;
            var selectedId = root["selectedId"]?.GetValue<string>();
            var returnRequested = root["returnRequested"]?.GetValue<bool>() == true;
            _staged = (root["items"] as JsonArray)?.Select(node =>
            {
                var item = node!.AsObject();
                return new StagedLogo(
                    item["id"]!.GetValue<string>(),
                    item["path"]!.GetValue<string>(),
                    item["thumbnailPath"]?.GetValue<string>() ?? item["path"]!.GetValue<string>(),
                    item["target"]!.GetValue<string>(),
                    item["typeLabel"]!.GetValue<string>());
            }).ToList() ?? [];
            _lastStateWrite = write;
            RefreshStagedList(selectedId);
            if (returnRequested && !_returnHandled)
            {
                _returnHandled = true;
                ReturnToApp();
            }
        }
        catch (IOException) { }
        catch (JsonException) { }
        finally { _readingState = false; }
    }

    private void ReturnToApp()
    {
        var window = Window.GetWindow(this) ?? Application.Current.MainWindow;
        if (window is null) return;
        if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
        window.Show();
        window.Activate();
        window.Topmost = true;
        window.Topmost = false;
        window.Focus();
        Status($"Returned from web Logo Creator with {_staged.Count} staged logo(s).");
    }

    private void RefreshStagedList(string? selectedId = null)
    {
        var selected = selectedId is null
            ? _stagedList.SelectedItem as StagedLogo
            : _staged.FirstOrDefault(item => item.Id == selectedId);
        _stagedList.ItemsSource = null;
        _stagedList.ItemsSource = _staged;
        if (selected is not null)
            _stagedList.SelectedItem = _staged.FirstOrDefault(item => item.Id == selected.Id);
        else if (_staged.Count > 0)
            _stagedList.SelectedIndex = _staged.Count - 1;
        _stageSummary.Text = _staged.Count == 0
            ? "Selections made in the browser will appear here."
            : $"{_staged.Count} logo{(_staged.Count == 1 ? "" : "s")} staged and ready for the Generator.";
    }

    private async Task ShowSelectedPreviewAsync()
    {
        if (_stagedList.SelectedItem is not StagedLogo item || !File.Exists(item.Path)) return;
        try
        {
            var result = (await Context.Bridge.CallAsync("image_thumbnail", new
            {
                path = item.Path,
                maximumWidth = 900,
                maximumHeight = 650,
            }))!.AsObject();
            if (_stagedList.SelectedItem is StagedLogo current && current.Id == item.Id)
                _preview.Load(result["path"]?.GetValue<string>());
        }
        catch (Exception ex) { Status(ex.Message); }
    }

    private void OnSend(object sender, RoutedEventArgs e)
    {
        if (_staged.Count == 0)
        {
            MessageBox.Show("Stage one or more logos in the web Logo Creator first.", "Logo Creator");
            return;
        }
        var logos = (JsonArray)Context.Project.Generator["logos"]!;
        foreach (var item in _staged)
        {
            if (item.Target == "front_wordmark")
            {
                Context.Project.SetImage("front_wordmark_image", item.Path);
                continue;
            }
            logos.Add(new JsonObject
            {
                { "path", item.Path }, { "targetName", item.Target },
                { "offsetX", 0 }, { "offsetY", 0 }, { "scalePercent", 100 },
                { "scaleWidthPercent", 100 }, { "scaleHeightPercent", 100 },
                { "rotationDegrees", 0 },
            });
        }
        Context.Project.MarkChanged();
        Status($"Sent {_staged.Count} staged logo(s) to Generator.");
    }
}

public sealed class TrimCreatorPage : ToolPageBase
{
    private readonly ImageViewport _reference=new(),_preview=new();private readonly TextBlock _readout=new(){Foreground=(System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"]};private readonly ComboBox _type=new();private readonly CheckBox _correct=new(){Content="Correct uneven lines and small gaps",IsChecked=true},_sharpen=new(){Content="Sharpen"},_color=new(){Content="Color correction"};private readonly ListBox _list=new();private readonly List<Point> _points=new();private readonly List<(string Path,string Type)> _staged=new();private string? _source,_current;
    public TrimCreatorPage(WorkspaceContext context):base(context){_reference.ImagePointClicked+=(_,p)=>Point(p);var left=new Grid();left.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});left.RowDefinitions.Add(new RowDefinition());left.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});left.Children.Add(Ui.Button("Upload Jersey Mockup",OnOpen,true));Grid.SetRow(_reference,1);left.Children.Add(_reference);Grid.SetRow(_readout,2);_readout.Margin=new Thickness(0,7,0,0);left.Children.Add(_readout);
        var right=new StackPanel();_preview.Height=220;right.Children.Add(_preview);foreach(var item in new[]{"Collar Trim","Left Arm Hole Trim","Right Arm Hole Trim","Waistband"})_type.Items.Add(item);_type.SelectedIndex=0;right.Children.Add(Ui.Row("Trim type",_type));var cleanup=new StackPanel();cleanup.Children.Add(_correct);cleanup.Children.Add(_sharpen);cleanup.Children.Add(_color);right.Children.Add(new GroupBox{Header="Cleanup",Content=cleanup});right.Children.Add(Ui.Buttons(Ui.Button("Stage Current Trim",OnStage,true),Ui.Button("Send Staged to Generator",OnSend)));right.Children.Add(Ui.Buttons(Ui.Button("Edit Selected Trim",(_,_)=>LoadSelected()),Ui.Button("Save Trim PNG As",OnSave)));_list.Height=120;right.Children.Add(new GroupBox{Header="Staged Trims",Content=_list});right.Children.Add(Ui.Buttons(Ui.Button("Remove Selected",OnRemove),Ui.Button("Clear",(_,_)=>{_staged.Clear();Refresh();})));Content=Ui.Page("Trim Creator","Upload a uniform photo, click two precise points across a trim, and create a new straight transparent trim strip.",Ui.Split(left,new ScrollViewer{Content=right,VerticalScrollBarVisibility=ScrollBarVisibility.Auto}));}
    private void OnOpen(object s,RoutedEventArgs e){var d=new OpenFileDialog{Filter="Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp|All files|*.*"};if(d.ShowDialog()!=true)return;_source=d.FileName;_points.Clear();_reference.Load(_source);_readout.Text="Click the first point, then the second point across the trim.";}
    private void Point(Point p){_points.Add(p);while(_points.Count>2)_points.RemoveAt(0);_readout.Text=_points.Count==1?$"First point: {p.X:0}, {p.Y:0}":$"Selected line: {_points[0].X:0}, {_points[0].Y:0} to {_points[1].X:0}, {_points[1].Y:0}";if(_points.Count==2)_=ProcessAsync();}
    private async Task ProcessAsync(){if(_source is null||_points.Count<2)return;try{var result=(await Context.Bridge.CallAsync("trim_process",new{path=_source,start=new[]{(int)_points[0].X,(int)_points[0].Y},end=new[]{(int)_points[1].X,(int)_points[1].Y},cropTop=0,cropBottom=0,correct=_correct.IsChecked==true}))!.AsObject();_current=result["path"]?.GetValue<string>();_preview.Load(_current);Status("Trim preview updated.");}catch(Exception ex){Error("Trim Creator",ex);}}
    private void OnStage(object s,RoutedEventArgs e){if(_current is null)return;_staged.Add((_current,_type.SelectedItem?.ToString()??"Collar Trim"));Refresh();}
    private void Refresh(){_list.ItemsSource=null;_list.ItemsSource=_staged.Select(x=>$"{x.Type} | {Path.GetFileName(x.Path)}").ToList();}
    private void OnSend(object s,RoutedEventArgs e){var keys=new Dictionary<string,string>{{"Collar Trim","collar_trim_image"},{"Left Arm Hole Trim","left_arm_hole_trim_image"},{"Right Arm Hole Trim","right_arm_hole_trim_image"},{"Waistband","waistband_image"}};foreach(var item in _staged)Context.Project.SetImage(keys[item.Type],item.Path);Status($"Sent {_staged.Count} staged trim(s) to Generator.");}
    private void LoadSelected(){if(_list.SelectedIndex<0)return;_current=_staged[_list.SelectedIndex].Path;_preview.Load(_current);}
    private void OnSave(object s,RoutedEventArgs e){if(_current is null)return;var d=new SaveFileDialog{Filter="PNG image|*.png",FileName="trim.png"};if(d.ShowDialog()==true)File.Copy(_current,d.FileName,true);}
    private void OnRemove(object s,RoutedEventArgs e){if(_list.SelectedIndex<0)return;_staged.RemoveAt(_list.SelectedIndex);Refresh();}
}

public sealed class TrimPathPage : ToolPageBase
{
    private readonly ImageViewport _view=new();private readonly TextBlock _readout=new(){Foreground=(System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"]};private readonly ComboBox _shape=new();private readonly TextBox _width=new(){Text="64"};private readonly CheckBox _mirrorPanel=new(){Content="Create opposite-panel copy"},_mirrorX=new(){Content="Create X-axis mirror"};private readonly ListBox _layers=new();private readonly List<Point> _points=new();private string? _pattern;
    public TrimPathPage(WorkspaceContext context):base(context){_view.ImagePointClicked+=(_,p)=>Point(p);_view.ImageRightClicked+=(_,_)=>_=FinishAsync();var left=new Grid();left.RowDefinitions.Add(new RowDefinition());left.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});left.Children.Add(_view);Grid.SetRow(_readout,1);_readout.Margin=new Thickness(0,7,0,0);left.Children.Add(_readout);var right=new StackPanel();right.Children.Add(Ui.Button("Choose Trim Pattern",OnPattern,true));foreach(var item in new[]{"Straight segments","Smooth curve","T shape"})_shape.Items.Add(item);_shape.SelectedIndex=0;right.Children.Add(Ui.Row("Path shape",_shape));right.Children.Add(Ui.Row("Trim width",_width));right.Children.Add(_mirrorPanel);right.Children.Add(_mirrorX);right.Children.Add(Ui.Buttons(Ui.Button("Finish Path",async(_,_)=>await FinishAsync(),true),Ui.Button("Undo Point",(_,_)=>Undo())));right.Children.Add(Ui.Button("Clear Points",(_,_)=>{_points.Clear();Readout();}));_layers.Height=220;right.Children.Add(new GroupBox{Header="Generator Trim Paths",Content=_layers});right.Children.Add(Ui.Button("Remove Selected Layer",OnRemove));Content=Ui.Page("Trim Path Lab","Draw multi-point trim paths over the active generator texture. Right-click finishes a path; mirrors become separate movable layers.",Ui.Split(left,new ScrollViewer{Content=right,VerticalScrollBarVisibility=ScrollBarVisibility.Auto},360));Loaded+=async(_,_)=>await BackgroundAsync();RefreshLayers();}
    protected override async void OnProjectReplaced(){RefreshLayers();await BackgroundAsync();}
    private async Task BackgroundAsync(){try{var result=(await Context.Bridge.CallAsync("render",new{project=Context.Project.Snapshot(),kind="preview"}))!.AsObject();_view.Load(result["path"]?.GetValue<string>());}catch(Exception ex){Status(ex.Message);}}
    private void OnPattern(object s,RoutedEventArgs e){var d=new OpenFileDialog{Filter="Trim PNG|*.png|Images|*.png;*.jpg;*.jpeg"};if(d.ShowDialog()==true){_pattern=d.FileName;Status($"Loaded trim pattern {Path.GetFileName(_pattern)}.");}}
    private void Point(Point p){if(_shape.SelectedItem?.ToString()=="T shape"&&_points.Count>=3)_points.Clear();_points.Add(p);Readout();}
    private void Readout(){var angle="--";if(_points.Count>1){var a=_points[^2];var b=_points[^1];angle=$"{Math.Atan2(b.Y-a.Y,b.X-a.X)*180/Math.PI:0.0} degrees";}_readout.Text=$"Points: {_points.Count} | Current angle: {angle} | Right-click to finish";}
    private void Undo(){if(_points.Count>0)_points.RemoveAt(_points.Count-1);Readout();}
    private async Task FinishAsync(){var needed=_shape.SelectedItem?.ToString()=="T shape"?3:2;if(_pattern is null||_points.Count<needed){Status($"Choose a trim and select at least {needed} points.");return;}try{var result=(await Context.Bridge.CallAsync("trim_path_render",new{pattern=_pattern,points=_points.Select(p=>new[]{p.X,p.Y}).ToArray(),shape=_shape.SelectedItem?.ToString(),trimWidth=int.TryParse(_width.Text,out var w)?w:64,mirrorPanel=_mirrorPanel.IsChecked==true,mirrorX=_mirrorX.IsChecked==true}))!.AsObject();var paths=result["paths"]!.AsArray();foreach(var path in paths){var array=(JsonArray)Context.Project.Generator["trimPathLayers"]!;var index=array.Count+1;array.Add(new JsonObject{{"name",$"Trim Path {index}"},{"path",path!.GetValue<string>()},{"garment",Context.Project.Garment},{"templateName",Context.Project.TemplateName},{"x",0},{"y",0},{"width",2048},{"height",2048},{"rotationDegrees",0},{"defaultX",0},{"defaultY",0},{"defaultWidth",2048},{"defaultHeight",2048}});}Context.Project.MarkChanged();_points.Clear();Readout();RefreshLayers();await BackgroundAsync();}catch(Exception ex){Error("Trim Path Lab",ex);}}
    private void RefreshLayers(){_layers.ItemsSource=null;_layers.ItemsSource=(Context.Project.Generator["trimPathLayers"] as JsonArray)?.Select(n=>$"{n?["name"]} | {n?["garment"]}").ToList();}
    private void OnRemove(object s,RoutedEventArgs e){if(_layers.SelectedIndex<0)return;((JsonArray)Context.Project.Generator["trimPathLayers"]!).RemoveAt(_layers.SelectedIndex);Context.Project.MarkChanged();RefreshLayers();}
}
