namespace Interleaver.Core;

public interface IInterleaverProfile
{
    string Kind { get; }
    IReadOnlyList<int> ToRegisters();
}
