namespace Interleaver.Core;

public sealed class SimpleInterleaverProfile : IInterleaverProfile
{
    public const int MinBranches = 2;
    public const int MaxBranches = 16;
    public int BranchCount { get; }
    public int DelayStepSymbols { get; }
    public string Kind => "simple";
    public SimpleInterleaverProfile(int branchCount, int delayStepSymbols)
    {
        if (branchCount is < MinBranches or > MaxBranches) throw new ArgumentOutOfRangeException(nameof(branchCount));
        if (delayStepSymbols < 0) throw new ArgumentOutOfRangeException(nameof(delayStepSymbols));
        BranchCount = branchCount; DelayStepSymbols = delayStepSymbols;
    }
    public IReadOnlyList<int> ToRegisters() => new[] { BranchCount, DelayStepSymbols };
}
