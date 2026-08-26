using System.Windows;

namespace JerseyModder.Wpf.Views;

public enum StartupChoice { None, New, Open }

public partial class StartupDialog : Window
{
    public StartupChoice Choice { get; private set; }
    public StartupDialog()
    {
        InitializeComponent();
        var version = typeof(StartupDialog).Assembly.GetName().Version;
        if (version is not null) VersionText.Text = $"Version {version.Major}.{version.Minor}.{version.Build}";
    }
    private void OnNew(object sender, RoutedEventArgs e) { Choice = StartupChoice.New; DialogResult = true; }
    private void OnOpen(object sender, RoutedEventArgs e) { Choice = StartupChoice.Open; DialogResult = true; }
    private void OnContinue(object sender, RoutedEventArgs e) { Choice = StartupChoice.None; DialogResult = false; }
}
