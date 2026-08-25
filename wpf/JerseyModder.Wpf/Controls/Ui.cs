using System.Windows;
using System.Windows.Controls;

namespace JerseyModder.Wpf.Controls;

public static class Ui
{
    public static Grid Page(string title, string description, UIElement body)
    {
        var root = new Grid { Margin = new Thickness(18, 16, 18, 16) };
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); root.RowDefinitions.Add(new RowDefinition());
        var header = new StackPanel { Margin = new Thickness(0, 0, 0, 14) };
        header.Children.Add(new TextBlock { Text = title, FontSize = 24, FontWeight = FontWeights.SemiBold });
        header.Children.Add(new TextBlock { Text = description, Foreground = (System.Windows.Media.Brush)Application.Current.Resources["MutedBrush"], Margin = new Thickness(0, 4, 0, 0), TextWrapping = TextWrapping.Wrap });
        Grid.SetRow(body, 1); root.Children.Add(header); root.Children.Add(body); return root;
    }

    public static Grid Split(UIElement left, UIElement right, double rightWidth = 390)
    {
        var grid = new Grid(); grid.ColumnDefinitions.Add(new ColumnDefinition()); grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(10) }); grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(rightWidth) });
        Grid.SetColumn(right, 2); grid.Children.Add(left); grid.Children.Add(right); return grid;
    }

    public static Grid Row(string label, UIElement input)
    {
        var grid = new Grid { Margin = new Thickness(0, 0, 0, 8) }; grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(125) }); grid.ColumnDefinitions.Add(new ColumnDefinition());
        grid.Children.Add(new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center }); Grid.SetColumn(input, 1); grid.Children.Add(input); return grid;
    }

    public static StackPanel Buttons(params Button[] buttons)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 8, 0, 8) }; foreach (var button in buttons) row.Children.Add(button); return row;
    }

    public static Button Button(string text, RoutedEventHandler handler, bool primary = false)
    {
        var button = new Button { Content = text }; if (primary) button.Style = (Style)Application.Current.Resources["PrimaryButton"]; button.Click += handler; return button;
    }
}
