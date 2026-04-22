using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using FlaUI.Core.AutomationElements;
using FlaUI.UIA3;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length > 0 && string.Equals(args[0], "serve", StringComparison.OrdinalIgnoreCase))
        {
            return NativeAutomationServer.Run(args[1..]);
        }

        try
        {
            var options = ProbeOptions.Parse(args);
            var report = NativeProbeRunner.Run(options);

            var jsonOptions = new JsonSerializerOptions
            {
                WriteIndented = !options.NoPrettyPrint,
                DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            };
            var json = JsonSerializer.Serialize(report, jsonOptions);

            if (!string.IsNullOrWhiteSpace(options.OutputPath))
            {
                var outputPath = Path.GetFullPath(options.OutputPath!);
                Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
                File.WriteAllText(outputPath, json);
                report.OutputPath = outputPath;
                json = JsonSerializer.Serialize(report, jsonOptions);
            }

            Console.WriteLine(json);
            return 0;
        }
        catch (ProbeUsageException ex)
        {
            Console.Error.WriteLine(ex.Message);
            PrintUsage();
            return 2;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"native-probe failed: {ex}");
            return 1;
        }
    }

    private static void PrintUsage()
    {
        Console.Error.WriteLine(
            """
            Usage:
              dotnet run --project native_runtime/VideoPlatform.NativeProbe -- [options]

            Options:
              serve [options]               Start the JSON-line native automation sidecar server.
              --repo-root <path>           Repository root for default output placement.
              --output <path>              Write JSON report to this file.
              --title-keyword <value>      Repeatable target window title keyword.
              --process-name <value>       Repeatable target process name. Default: ClientFrame.exe
              --render-process-name <val>  Repeatable render-surface process name. Default: VSClient.exe
              --open-layout-panel          Try invoking the "窗口分割" control, then rescan related windows.
              --tree-depth <n>             Descendant scan depth. Default: 4
              --no-pretty                  Disable indented JSON output.
              --help                       Show this message.
            """
        );
    }
}

internal sealed class ProbeUsageException : Exception
{
    public ProbeUsageException(string message) : base(message)
    {
    }
}

internal sealed class ProbeOptions
{
    public string? RepoRoot { get; private set; }
    public string? OutputPath { get; private set; }
    public bool OpenLayoutPanel { get; private set; }
    public bool NoPrettyPrint { get; private set; }
    public int TreeDepth { get; private set; } = 4;
    public List<string> TitleKeywords { get; } = ["视频融合赋能平台", "视频监控"];
    public List<string> ProcessNames { get; } = ["ClientFrame.exe"];
    public List<string> RenderProcessNames { get; } = ["VSClient.exe"];

    public static ProbeOptions Parse(string[] args)
    {
        var options = new ProbeOptions();
        var clearTitleKeywords = false;
        var clearProcessNames = false;
        var clearRenderProcessNames = false;

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--repo-root":
                    options.RepoRoot = RequireValue(args, ref i, "--repo-root");
                    break;
                case "--output":
                    options.OutputPath = RequireValue(args, ref i, "--output");
                    break;
                case "--title-keyword":
                    if (!clearTitleKeywords)
                    {
                        clearTitleKeywords = true;
                        options.TitleKeywords.Clear();
                    }
                    options.TitleKeywords.Add(RequireValue(args, ref i, "--title-keyword"));
                    break;
                case "--process-name":
                    if (!clearProcessNames)
                    {
                        clearProcessNames = true;
                        options.ProcessNames.Clear();
                    }
                    options.ProcessNames.Add(RequireValue(args, ref i, "--process-name"));
                    break;
                case "--render-process-name":
                    if (!clearRenderProcessNames)
                    {
                        clearRenderProcessNames = true;
                        options.RenderProcessNames.Clear();
                    }
                    options.RenderProcessNames.Add(RequireValue(args, ref i, "--render-process-name"));
                    break;
                case "--open-layout-panel":
                    options.OpenLayoutPanel = true;
                    break;
                case "--tree-depth":
                    if (!int.TryParse(RequireValue(args, ref i, "--tree-depth"), out var treeDepth) || treeDepth < 1 || treeDepth > 12)
                    {
                        throw new ProbeUsageException("--tree-depth must be an integer between 1 and 12.");
                    }
                    options.TreeDepth = treeDepth;
                    break;
                case "--no-pretty":
                    options.NoPrettyPrint = true;
                    break;
                case "--help":
                case "-h":
                case "/?":
                    throw new ProbeUsageException("Help requested.");
                default:
                    throw new ProbeUsageException($"Unknown option: {args[i]}");
            }
        }

        if (options.TitleKeywords.Count == 0)
        {
            throw new ProbeUsageException("At least one --title-keyword is required.");
        }
        if (options.ProcessNames.Count == 0)
        {
            throw new ProbeUsageException("At least one --process-name is required.");
        }

        if (string.IsNullOrWhiteSpace(options.OutputPath))
        {
            var repoRoot = !string.IsNullOrWhiteSpace(options.RepoRoot)
                ? options.RepoRoot!
                : Directory.GetCurrentDirectory();
            options.OutputPath = Path.Combine(repoRoot, "tmp", "native_uia_probe.json");
        }

        return options;
    }

    private static string RequireValue(string[] args, ref int index, string optionName)
    {
        if (index + 1 >= args.Length)
        {
            throw new ProbeUsageException($"Missing value for {optionName}");
        }
        index += 1;
        return args[index];
    }
}

internal static class NativeProbeRunner
{
    private static readonly string[] WindowedMarkers =
    [
        "收藏夹",
        "打开文件夹",
        "搜索",
        "全部收藏",
        "视频监控配置",
    ];

    private static readonly string[] LayoutPanelNames =
    [
        "窗口分割",
        "平均",
        "高亮分割",
        "水平",
        "垂直",
        "其他",
        "4",
        "6",
        "9",
        "12",
        "13",
    ];

    private static readonly string[] ModeControlNames =
    [
        "全屏",
        "退出全屏",
    ];

    public static NativeProbeReport Run(ProbeOptions options)
    {
        using var automation = new UIA3Automation();
        var desktopWindows = Win32WindowInspector.EnumerateVisibleWindows();
        var targetWindows = desktopWindows
            .Where(window => MatchesTarget(window, options))
            .OrderByDescending(window => window.IsForeground)
            .ThenByDescending(window => window.Area)
            .ToList();

        var report = new NativeProbeReport
        {
            TimestampUtc = DateTimeOffset.UtcNow,
            Host = Environment.MachineName,
            RepoRoot = options.RepoRoot ?? Directory.GetCurrentDirectory(),
            Query = new ProbeQuerySummary
            {
                TitleKeywords = [.. options.TitleKeywords],
                ProcessNames = [.. options.ProcessNames],
                RenderProcessNames = [.. options.RenderProcessNames],
                OpenLayoutPanel = options.OpenLayoutPanel,
                TreeDepth = options.TreeDepth,
            },
        };

        foreach (var target in targetWindows)
        {
            report.Targets.Add(InspectTarget(target, desktopWindows, automation, options));
        }

        report.Decision = BuildDecision(report.Targets, options);
        return report;
    }

    private static TargetWindowProbe InspectTarget(
        Win32WindowInfo target,
        IReadOnlyList<Win32WindowInfo> desktopWindows,
        UIA3Automation automation,
        ProbeOptions options)
    {
        var probe = new TargetWindowProbe
        {
            MainWindow = target,
        };

        var mainElement = TryFromHandle(automation, target.Hwnd);
        if (mainElement is null)
        {
            probe.Notes.Add("UIA 无法从主窗口句柄附着 AutomationElement。");
            return probe;
        }

        probe.MainWindowElement = ElementSnapshot.From(mainElement, target.Hwnd, "main_window_root");
        probe.PreOpenMatches.AddRange(ScanInterestingControls(mainElement, target.Hwnd, "main", options.TreeDepth));

        var relatedWindows = desktopWindows
            .Where(window => window.Hwnd != target.Hwnd && IsRelatedWindow(target, window, options))
            .OrderByDescending(window => window.Area)
            .ToList();
        probe.RelatedWindows.AddRange(relatedWindows);

        foreach (var related in relatedWindows)
        {
            var relatedElement = TryFromHandle(automation, related.Hwnd);
            if (relatedElement is null)
            {
                continue;
            }
            probe.RelatedWindowRoots.Add(ElementSnapshot.From(relatedElement, related.Hwnd, "related_window_root"));
            probe.PreOpenMatches.AddRange(ScanInterestingControls(relatedElement, related.Hwnd, SourceLabelForWindow(target, related, options), options.TreeDepth));
        }

        if (options.OpenLayoutPanel)
        {
            var splitControl = FindFirstControlByName(automation, target, relatedWindows, "窗口分割", options.TreeDepth);
            if (splitControl is null)
            {
                probe.Notes.Add("未在主窗口及相关窗口中找到“窗口分割”控件，无法继续做主动展开验证。");
            }
            else
            {
                probe.LayoutPanelOpenAttempt = TryInvoke(splitControl);
                Thread.Sleep(800);

                var rescannedWindows = Win32WindowInspector.EnumerateVisibleWindows()
                    .Where(window => window.Hwnd == target.Hwnd || IsRelatedWindow(target, window, options))
                    .OrderByDescending(window => window.Area)
                    .ToList();
                foreach (var rescanned in rescannedWindows)
                {
                    var element = TryFromHandle(automation, rescanned.Hwnd);
                    if (element is null)
                    {
                        continue;
                    }
                    probe.PostOpenMatches.AddRange(ScanInterestingControls(element, rescanned.Hwnd, SourceLabelForWindow(target, rescanned, options), options.TreeDepth));
                }
            }
        }

        var allMatches = probe.AllMatches();
        probe.Capabilities = new ProbeCapabilities
        {
            FoundWindowSplitControl = allMatches.Any(match => NameEquals(match.Name, "窗口分割")),
            FoundFullscreenToggle = allMatches.Any(match => ModeControlNames.Any(name => NameEquals(match.Name, name))),
            FoundWindowedMarkers = allMatches.Count(match => WindowedMarkers.Any(name => NameEquals(match.Name, name))),
            FoundLayoutSections = allMatches.Count(match => new[] { "平均", "高亮分割", "水平", "垂直", "其他" }.Any(name => NameEquals(match.Name, name))),
            FoundLayoutOptions = allMatches.Count(match => new[] { "4", "6", "9", "12", "13" }.Any(name => NameEquals(match.Name, name))),
            RelatedRenderSurfaceCount = relatedWindows.Count(window => IsRenderSurfaceProcess(window, options)),
            RenderSurfaceInterestingElementCount = allMatches.Count(match => match.Source.Contains("render_surface", StringComparison.OrdinalIgnoreCase)),
        };

        if (probe.Capabilities.RelatedRenderSurfaceCount > 0 && probe.Capabilities.RenderSurfaceInterestingElementCount == 0)
        {
            probe.Notes.Add("检测到 VSClient 类渲染窗，但该渲染窗没有暴露出可用的 UIA 关键控件。");
        }
        if (!probe.Capabilities.FoundWindowSplitControl)
        {
            probe.Notes.Add("未找到“窗口分割”控件。");
        }
        if (!probe.Capabilities.FoundFullscreenToggle)
        {
            probe.Notes.Add("未找到“全屏/退出全屏”控件。");
        }
        if (options.OpenLayoutPanel && probe.Capabilities.FoundLayoutOptions == 0)
        {
            probe.Notes.Add("主动展开后仍未枚举到布局项，说明布局面板大概率不适合依赖 UIA 做稳定读写。");
        }

        return probe;
    }

    private static ProbeDecision BuildDecision(IReadOnlyList<TargetWindowProbe> targets, ProbeOptions options)
    {
        if (targets.Count == 0)
        {
            return new ProbeDecision
            {
                RecommendedPath = "sdk_or_web_plugin",
                Summary = "没有找到目标客户端主窗口。当前原生 UIA3 探针无法建立稳定入口。",
            };
        }

        var best = targets
            .OrderByDescending(target => target.MainWindow.IsForeground)
            .ThenByDescending(target => target.MainWindow.Area)
            .First();
        var caps = best.Capabilities ?? new ProbeCapabilities();

        var canDriveToolbarWithUia = caps.FoundWindowSplitControl && caps.FoundFullscreenToggle;
        var canReadLayoutPanelWithUia = caps.FoundLayoutSections > 0 || caps.FoundLayoutOptions > 0;
        var renderSurfaceInvisibleToUia = caps.RelatedRenderSurfaceCount > 0 && caps.RenderSurfaceInterestingElementCount == 0;

        if (canDriveToolbarWithUia && canReadLayoutPanelWithUia)
        {
            return new ProbeDecision
            {
                RecommendedPath = renderSurfaceInvisibleToUia ? "hybrid_native_uia_plus_sdk_or_readback" : "native_uia_candidate",
                Summary = renderSurfaceInvisibleToUia
                    ? "顶部工具栏和布局面板可以继续验证 UIA 迁移，但视频渲染面没有可靠 UIA 回读，不能再把视频内容识别当主状态源。"
                    : "关键工具栏控件和布局面板已可枚举，原生 UIA 迁移具备初步可行性。",
            };
        }

        return new ProbeDecision
        {
            RecommendedPath = "sdk_or_web_plugin",
            Summary = options.OpenLayoutPanel
                ? "即使主动展开布局面板，关键布局项仍不能稳定通过 UIA 枚举。应优先转平台 SDK / Web 插件路线。"
                : "关键控件未完整暴露给 UIA。若后续主动展开验证仍不通，应直接转平台 SDK / Web 插件路线。",
        };
    }

    private static bool MatchesTarget(Win32WindowInfo window, ProbeOptions options)
    {
        var processMatch = options.ProcessNames.Any(processName =>
            NormalizeProcessName(window.ProcessName) == NormalizeProcessName(processName));
        var titleMatch = options.TitleKeywords.Any(keyword =>
            window.Title.Contains(keyword, StringComparison.OrdinalIgnoreCase));
        return window.IsVisible && (processMatch || titleMatch);
    }

    private static bool IsRelatedWindow(Win32WindowInfo target, Win32WindowInfo other, ProbeOptions options)
    {
        if (!other.IsVisible)
        {
            return false;
        }
        if (other.Hwnd == target.Hwnd)
        {
            return false;
        }
        if (other.OwnerHwnd == target.Hwnd)
        {
            return true;
        }
        if (other.ProcessId == target.ProcessId && target.Bounds.IntersectionRatio(other.Bounds) >= 0.10)
        {
            return true;
        }
        if (IsRenderSurfaceProcess(other, options) && target.Bounds.IntersectionRatio(other.Bounds) >= 0.80)
        {
            return true;
        }
        return false;
    }

    private static bool IsRenderSurfaceProcess(Win32WindowInfo window, ProbeOptions options)
    {
        return options.RenderProcessNames.Any(processName =>
            NormalizeProcessName(window.ProcessName) == NormalizeProcessName(processName));
    }

    private static string SourceLabelForWindow(Win32WindowInfo target, Win32WindowInfo window, ProbeOptions options)
    {
        if (window.Hwnd == target.Hwnd)
        {
            return "main";
        }
        if (IsRenderSurfaceProcess(window, options))
        {
            return "render_surface";
        }
        if (window.OwnerHwnd == target.Hwnd)
        {
            return "owned_popup";
        }
        return "related_window";
    }

    private static string NormalizeProcessName(string? processName)
    {
        var normalized = (processName ?? string.Empty).Trim();
        if (normalized.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
        {
            return normalized.ToLowerInvariant();
        }
        return $"{normalized}.exe".ToLowerInvariant();
    }

    private static AutomationElement? TryFromHandle(UIA3Automation automation, IntPtr hwnd)
    {
        try
        {
            return automation.FromHandle(hwnd);
        }
        catch
        {
            return null;
        }
    }

    private static List<ElementSnapshot> ScanInterestingControls(
        AutomationElement root,
        IntPtr sourceWindowHwnd,
        string sourceLabel,
        int maxDepth)
    {
        var results = new List<ElementSnapshot>();
        var queue = new Queue<(AutomationElement Element, int Depth)>();
        queue.Enqueue((root, 0));

        while (queue.Count > 0)
        {
            var (current, depth) = queue.Dequeue();
            if (IsInterestingControl(current))
            {
                results.Add(ElementSnapshot.From(current, sourceWindowHwnd, sourceLabel));
            }

            if (depth >= maxDepth)
            {
                continue;
            }

            AutomationElement[] children;
            try
            {
                children = current.FindAllChildren();
            }
            catch
            {
                continue;
            }

            foreach (var child in children)
            {
                queue.Enqueue((child, depth + 1));
            }
        }

        return results;
    }

    private static bool IsInterestingControl(AutomationElement element)
    {
        var name = (element.Name ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(name))
        {
            return false;
        }

        return WindowedMarkers.Any(marker => NameEquals(name, marker))
            || LayoutPanelNames.Any(marker => NameEquals(name, marker))
            || ModeControlNames.Any(marker => NameEquals(name, marker));
    }

    private static bool NameEquals(string? actual, string expected)
    {
        return string.Equals((actual ?? string.Empty).Trim(), expected, StringComparison.OrdinalIgnoreCase);
    }

    private static AutomationElement? FindFirstControlByName(
        UIA3Automation automation,
        Win32WindowInfo target,
        IEnumerable<Win32WindowInfo> relatedWindows,
        string controlName,
        int maxDepth)
    {
        var roots = new List<Win32WindowInfo> { target };
        roots.AddRange(relatedWindows);

        foreach (var window in roots)
        {
            var root = TryFromHandle(automation, window.Hwnd);
            if (root is null)
            {
                continue;
            }
            var queue = new Queue<(AutomationElement Element, int Depth)>();
            queue.Enqueue((root, 0));

            while (queue.Count > 0)
            {
                var (current, depth) = queue.Dequeue();
                if (NameEquals(current.Name, controlName))
                {
                    return current;
                }
                if (depth >= maxDepth)
                {
                    continue;
                }
                AutomationElement[] children;
                try
                {
                    children = current.FindAllChildren();
                }
                catch
                {
                    continue;
                }
                foreach (var child in children)
                {
                    queue.Enqueue((child, depth + 1));
                }
            }
        }

        return null;
    }

    private static InvokeAttempt TryInvoke(AutomationElement element)
    {
        var attempt = new InvokeAttempt
        {
            Element = ElementSnapshot.From(element, IntPtr.Zero, "invoke_target"),
        };

        try
        {
            element.Focus();
        }
        catch (Exception ex)
        {
            attempt.Notes.Add($"focus failed: {ex.Message}");
        }

        try
        {
            var invoke = element.Patterns.Invoke.PatternOrDefault;
            if (invoke is not null)
            {
                invoke.Invoke();
                attempt.Success = true;
                attempt.Method = "InvokePattern";
                return attempt;
            }
        }
        catch (Exception ex)
        {
            attempt.Notes.Add($"invoke pattern failed: {ex.Message}");
        }

        try
        {
            var legacy = element.Patterns.LegacyIAccessible.PatternOrDefault;
            if (legacy is not null)
            {
                legacy.DoDefaultAction();
                attempt.Success = true;
                attempt.Method = "LegacyIAccessible.DoDefaultAction";
                return attempt;
            }
        }
        catch (Exception ex)
        {
            attempt.Notes.Add($"legacy action failed: {ex.Message}");
        }

        attempt.Success = false;
        attempt.Method = "none";
        return attempt;
    }
}

internal static class Win32WindowInspector
{
    public static List<Win32WindowInfo> EnumerateVisibleWindows()
    {
        var foreground = GetForegroundWindow();
        var windows = new List<Win32WindowInfo>();
        EnumWindows((hwnd, _) =>
        {
            if (hwnd == IntPtr.Zero || !IsWindowVisible(hwnd))
            {
                return true;
            }

            if (!TryGetWindowRect(hwnd, out var rect) || rect.Width <= 0 || rect.Height <= 0)
            {
                return true;
            }

            var title = GetWindowTextManaged(hwnd);
            var processId = GetWindowProcessId(hwnd);
            var processName = TryGetProcessName(processId);
            var owner = GetWindow(hwnd, 4);

            windows.Add(new Win32WindowInfo
            {
                Hwnd = hwnd,
                Title = title,
                ProcessId = processId,
                ProcessName = processName,
                OwnerHwnd = owner,
                IsVisible = true,
                IsForeground = hwnd == foreground,
                Bounds = new RectDto(rect.Left, rect.Top, rect.Right, rect.Bottom),
            });

            return true;
        }, IntPtr.Zero);

        return windows;
    }

    public static int GetProcessId(IntPtr hwnd)
    {
        return GetWindowProcessId(hwnd);
    }

    private static string GetWindowTextManaged(IntPtr hwnd)
    {
        var length = GetWindowTextLength(hwnd);
        var buffer = new System.Text.StringBuilder(length + 1);
        _ = GetWindowText(hwnd, buffer, buffer.Capacity);
        return buffer.ToString();
    }

    private static int GetWindowProcessId(IntPtr hwnd)
    {
        _ = GetWindowThreadProcessId(hwnd, out var processId);
        return unchecked((int)processId);
    }

    private static string TryGetProcessName(int processId)
    {
        try
        {
            return $"{Process.GetProcessById(processId).ProcessName}.exe";
        }
        catch
        {
            return string.Empty;
        }
    }

    private static bool TryGetWindowRect(IntPtr hwnd, out RECT rect)
    {
        return GetWindowRect(hwnd, out rect);
    }

    private delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr hWnd, uint uCmd);

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;

        public int Width => Math.Max(0, Right - Left);
        public int Height => Math.Max(0, Bottom - Top);
    }
}

internal sealed class NativeProbeReport
{
    public DateTimeOffset TimestampUtc { get; set; }
    public string Host { get; set; } = string.Empty;
    public string RepoRoot { get; set; } = string.Empty;
    public string? OutputPath { get; set; }
    public ProbeQuerySummary Query { get; set; } = new();
    public List<TargetWindowProbe> Targets { get; set; } = [];
    public ProbeDecision Decision { get; set; } = new();
}

internal sealed class ProbeQuerySummary
{
    public List<string> TitleKeywords { get; set; } = [];
    public List<string> ProcessNames { get; set; } = [];
    public List<string> RenderProcessNames { get; set; } = [];
    public bool OpenLayoutPanel { get; set; }
    public int TreeDepth { get; set; }
}

internal sealed class TargetWindowProbe
{
    public Win32WindowInfo MainWindow { get; set; } = new();
    public ElementSnapshot? MainWindowElement { get; set; }
    public List<Win32WindowInfo> RelatedWindows { get; set; } = [];
    public List<ElementSnapshot> RelatedWindowRoots { get; set; } = [];
    public List<ElementSnapshot> PreOpenMatches { get; set; } = [];
    public InvokeAttempt? LayoutPanelOpenAttempt { get; set; }
    public List<ElementSnapshot> PostOpenMatches { get; set; } = [];
    public ProbeCapabilities? Capabilities { get; set; }
    public List<string> Notes { get; set; } = [];

    public IEnumerable<ElementSnapshot> AllMatches() => PreOpenMatches.Concat(PostOpenMatches);
}

internal sealed class ProbeCapabilities
{
    public bool FoundWindowSplitControl { get; set; }
    public bool FoundFullscreenToggle { get; set; }
    public int FoundWindowedMarkers { get; set; }
    public int FoundLayoutSections { get; set; }
    public int FoundLayoutOptions { get; set; }
    public int RelatedRenderSurfaceCount { get; set; }
    public int RenderSurfaceInterestingElementCount { get; set; }
}

internal sealed class InvokeAttempt
{
    public bool Success { get; set; }
    public string Method { get; set; } = string.Empty;
    public ElementSnapshot? Element { get; set; }
    public List<string> Notes { get; set; } = [];
}

internal sealed class ProbeDecision
{
    public string RecommendedPath { get; set; } = string.Empty;
    public string Summary { get; set; } = string.Empty;
}

internal sealed class Win32WindowInfo
{
    [JsonIgnore]
    public IntPtr Hwnd { get; set; }
    public string HwndHex => $"0x{Hwnd.ToInt64():X}";
    public int ProcessId { get; set; }
    public string ProcessName { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    [JsonIgnore]
    public IntPtr OwnerHwnd { get; set; }
    public string OwnerHwndHex => $"0x{OwnerHwnd.ToInt64():X}";
    public bool IsVisible { get; set; }
    public bool IsForeground { get; set; }
    public RectDto Bounds { get; set; } = new();

    [JsonIgnore]
    public int Area => Bounds.Width * Bounds.Height;
}

internal sealed class ElementSnapshot
{
    public string Source { get; set; } = string.Empty;
    [JsonIgnore]
    public IntPtr SourceWindowHwnd { get; set; }
    public string SourceWindowHwndHex => $"0x{SourceWindowHwnd.ToInt64():X}";
    public string Name { get; set; } = string.Empty;
    public string AutomationId { get; set; } = string.Empty;
    public string ClassName { get; set; } = string.Empty;
    public string ControlType { get; set; } = string.Empty;
    public string FrameworkType { get; set; } = string.Empty;
    public int ProcessId { get; set; }
    public RectDto Bounds { get; set; } = new();

    public static ElementSnapshot From(AutomationElement element, IntPtr sourceWindowHwnd, string source)
    {
        var bounds = SafeGetBounds(element);
        return new ElementSnapshot
        {
            Source = source,
            SourceWindowHwnd = sourceWindowHwnd,
            Name = SafeGetString(() => element.Name),
            AutomationId = SafeGetString(() => element.AutomationId),
            ClassName = SafeGetString(() => element.ClassName),
            ControlType = SafeGetString(() => element.ControlType.ToString()),
            FrameworkType = SafeGetString(() => element.FrameworkType.ToString()),
            ProcessId = sourceWindowHwnd != IntPtr.Zero ? Win32WindowInspector.GetProcessId(sourceWindowHwnd) : 0,
            Bounds = new RectDto(
                bounds.Left,
                bounds.Top,
                bounds.Right,
                bounds.Bottom
            ),
        };
    }

    private static RectDto SafeGetBounds(AutomationElement element)
    {
        try
        {
            var bounds = element.BoundingRectangle;
            return new RectDto(
                Convert.ToInt32(bounds.Left),
                Convert.ToInt32(bounds.Top),
                Convert.ToInt32(bounds.Right),
                Convert.ToInt32(bounds.Bottom)
            );
        }
        catch
        {
            return new RectDto(0, 0, 0, 0);
        }
    }

    private static string SafeGetString(Func<string> getter)
    {
        try
        {
            return getter() ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }
}

internal sealed class RectDto
{
    public RectDto()
    {
    }

    public RectDto(int left, int top, int right, int bottom)
    {
        Left = left;
        Top = top;
        Right = right;
        Bottom = bottom;
    }

    public int Left { get; set; }
    public int Top { get; set; }
    public int Right { get; set; }
    public int Bottom { get; set; }

    [JsonIgnore]
    public int Width => Math.Max(0, Right - Left);

    [JsonIgnore]
    public int Height => Math.Max(0, Bottom - Top);

    [JsonIgnore]
    public int Area => Width * Height;

    public double IntersectionRatio(RectDto other)
    {
        var left = Math.Max(Left, other.Left);
        var top = Math.Max(Top, other.Top);
        var right = Math.Min(Right, other.Right);
        var bottom = Math.Min(Bottom, other.Bottom);
        var width = Math.Max(0, right - left);
        var height = Math.Max(0, bottom - top);
        var intersectionArea = width * height;
        if (intersectionArea <= 0)
        {
            return 0.0;
        }

        return intersectionArea / (double)Math.Max(1, Math.Min(Area, other.Area));
    }
}
