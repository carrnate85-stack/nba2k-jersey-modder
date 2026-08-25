using System.Windows;

namespace JerseyModder.Wpf;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += (_, args) =>
        {
            MessageBox.Show(args.Exception.Message, "NBA 2K Jersey Modder", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };
    }
}
