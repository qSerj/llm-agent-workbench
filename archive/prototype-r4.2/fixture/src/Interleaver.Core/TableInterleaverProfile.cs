namespace Interleaver.Core;

public sealed class TableInterleaverProfile : IInterleaverProfile
{
    public const int MinEntries = 2;
    public const int MaxEntries = 32;
    private readonly int[] _delays;
    public string Kind => "table";
    public IReadOnlyList<int> Delays => _delays;
    public TableInterleaverProfile(IEnumerable<int> delays)
    {
        ArgumentNullException.ThrowIfNull(delays);
        _delays = delays.ToArray();
        if (_delays.Length is < MinEntries or > MaxEntries) throw new ArgumentOutOfRangeException(nameof(delays));
        if (_delays.Any(x => x < 0)) throw new ArgumentOutOfRangeException(nameof(delays));
    }
    public IReadOnlyList<int> ToRegisters() => _delays;
}
