using System.Windows;
using JerseyModder.Wpf.Models;
using JerseyModder.Wpf.Services;
using JerseyModder.Wpf.Views;
using Microsoft.Win32;

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
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        var initialProject = ChooseStartupProject();
        var mainWindow = new MainWindow(initialProject);
        MainWindow = mainWindow;
        ShutdownMode = ShutdownMode.OnMainWindowClose;
        mainWindow.Show();
    }

    private static ProjectStore? ChooseStartupProject()
    {
        while (true)
        {
            var welcome = new StartupDialog { WindowStartupLocation = WindowStartupLocation.CenterScreen, ShowInTaskbar = true };
            welcome.ShowDialog();
            if (welcome.Choice == StartupChoice.None) return null;

            if (welcome.Choice == StartupChoice.New)
            {
                var dialog = new NewProjectDialog { WindowStartupLocation = WindowStartupLocation.CenterScreen, ShowInTaskbar = true };
                if (dialog.ShowDialog() != true) continue;
                try
                {
                    var path = ProjectWorkspace.Create(dialog.ParentFolder, dialog.ProjectName);
                    var project = new ProjectStore();
                    project.SaveAsync(path).GetAwaiter().GetResult();
                    return project;
                }
                catch (Exception ex)
                {
                    MessageBox.Show(ex.Message, "Create Project", MessageBoxButton.OK, MessageBoxImage.Error);
                }
                continue;
            }

            var open = new OpenFileDialog
            {
                Title = "Open jersey project",
                Filter = "NBA 2K projects (*.nba2kproject.json;*.json)|*.nba2kproject.json;*.json|All files|*.*",
            };
            if (open.ShowDialog() != true) continue;
            try
            {
                ProjectWorkspace.EnsureStructure(open.FileName);
                return ProjectStore.LoadAsync(open.FileName).GetAwaiter().GetResult();
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "Open Project", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
    }
}
