using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace JerseyModder.Wpf.Views;

public partial class ColorPickerWindow : Window
{
    private bool _syncing;
    public string SelectedHex { get; private set; } = "#ffffff";
    private static readonly string[] Swatches =
    {
        "#ffffff", "#d9d9d9", "#808080", "#202020", "#000000",
        "#c8102e", "#ed174c", "#f15a22", "#fdb927", "#ffd700",
        "#008348", "#00a650", "#00a9e0", "#006bb6", "#1d428a",
        "#552583", "#702f8a", "#862633", "#ce1141", "#0e2240",
    };

    public ColorPickerWindow(string initial)
    {
        InitializeComponent();
        foreach (var value in Swatches)
        {
            var button = new Button
            {
                Width = 32, Height = 32, Padding = new Thickness(0), Margin = new Thickness(3),
                Background = new SolidColorBrush(Parse(value)), ToolTip = value, Tag = value,
            };
            button.Click += OnSwatch;
            Palette.Children.Add(button);
        }
        SetColor(IsHex(initial) ? initial : "#ffffff");
    }

    public static string? Pick(Window? owner, string initial)
    {
        var dialog = new ColorPickerWindow(initial) { Owner = owner };
        return dialog.ShowDialog() == true ? dialog.SelectedHex : null;
    }

    private void OnSwatch(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: string value }) SetColor(value);
    }

    private void OnRgbChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_syncing) return;
        SetColor($"#{(int)Red.Value:x2}{(int)Green.Value:x2}{(int)Blue.Value:x2}");
    }

    private void OnHexChanged(object sender, TextChangedEventArgs e)
    {
        if (!_syncing && IsHex(HexValue.Text)) SetColor(HexValue.Text);
    }

    private void SetColor(string value)
    {
        var color = Parse(value);
        _syncing = true;
        SelectedHex = $"#{color.R:x2}{color.G:x2}{color.B:x2}";
        HexValue.Text = SelectedHex;
        Red.Value = color.R; Green.Value = color.G; Blue.Value = color.B;
        RedText.Text = color.R.ToString(CultureInfo.InvariantCulture);
        GreenText.Text = color.G.ToString(CultureInfo.InvariantCulture);
        BlueText.Text = color.B.ToString(CultureInfo.InvariantCulture);
        ColorPreview.Background = new SolidColorBrush(color);
        _syncing = false;
    }

    private void OnAccept(object sender, RoutedEventArgs e)
    {
        if (!IsHex(HexValue.Text))
        {
            MessageBox.Show("Enter a six-digit hex color such as #1d428a.", "Choose Color", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        SetColor(HexValue.Text); DialogResult = true;
    }

    private static bool IsHex(string? value) => value is { Length: 7 } && value[0] == '#' && int.TryParse(value[1..], NumberStyles.HexNumber, CultureInfo.InvariantCulture, out _);
    private static Color Parse(string value) { var number = int.Parse(value[1..], NumberStyles.HexNumber, CultureInfo.InvariantCulture); return Color.FromRgb((byte)(number >> 16), (byte)(number >> 8), (byte)number); }
}
