# Interleaver Profiles

> Source files: `src/Interleaver.Core/IInterleaverProfile.cs`, `src/Interleaver.Core/SimpleInterleaverProfile.cs`, `src/Interleaver.Core/TableInterleaverProfile.cs`, `src/Interleaver.Transport/DeviceController.cs`, `src/Interleaver.Transport/ProfileUsageExample.cs`

## Public Abstraction

`IInterleaverProfile` (`IInterleaverProfile.cs:3`) is the sole public interface for all interleaver profiles. It defines:

- **`Kind`** (`string`, read-only) — A discriminator that identifies the profile type.
- **`ToRegisters()`** (`IReadOnlyList<int>`) — Serialises the profile into a flat list of integer register values for transmission to hardware.

All validation and encoding logic lives in the concrete implementations. The transport layer consumes profiles exclusively through this interface.

## Concrete Implementations

### 1. `SimpleInterleaverProfile`

**Source:** `src/Interleaver.Core/SimpleInterleaverProfile.cs:3`

A compact profile that parameterises an interleaver with two values: a branch count and a per-branch delay step.

| Property | Type | Description |
|---|---|---|
| `BranchCount` | `int` | Number of interleaver branches (must be 2–16) |
| `DelayStepSymbols` | `int` | Delay increment between consecutive branches (must be ≥ 0) |
| `Kind` | `string` | Always `"simple"` |

#### Validation

| Constant | Value | Meaning |
|---|---|---|
| `MinBranches` | 2 | Minimum allowed `BranchCount` |
| `MaxBranches` | 16 | Maximum allowed `BranchCount` |

- `branchCount` must satisfy `MinBranches <= branchCount <= MaxBranches`, otherwise `ArgumentOutOfRangeException` is thrown.
- `delayStepSymbols` must be `>= 0`, otherwise `ArgumentOutOfRangeException` is thrown.

#### `ToRegisters()` encoding

Returns a two-element array: `[ BranchCount, DelayStepSymbols ]`.

| Index | Value | Register purpose |
|---|---|---|
| 0 | `BranchCount` | Number of branches to configure |
| 1 | `DelayStepSymbols` | Delay step in symbols between branches |

### 2. `TableInterleaverProfile`

**Source:** `src/Interleaver.Core/TableInterleaverProfile.cs:3`

A flexible profile that stores an explicit delay table — one delay value per branch.

| Property | Type | Description |
|---|---|---|
| `Delays` | `IReadOnlyList<int>` | Copy of the delay values passed at construction |
| `Kind` | `string` | Always `"table"` |

#### Validation

| Constant | Value | Meaning |
|---|---|---|
| `MinEntries` | 2 | Minimum number of delay entries |
| `MaxEntries` | 32 | Maximum number of delay entries |

- The `delays` enumerable must not be `null` (checked via `ArgumentNullException.ThrowIfNull`).
- After materialisation, the resulting array length must satisfy `MinEntries <= length <= MaxEntries`, otherwise `ArgumentOutOfRangeException` is thrown.
- Every individual delay value must be `>= 0`, otherwise `ArgumentOutOfRangeException` is thrown.

#### `ToRegisters()` encoding

Returns the delay array directly: `[ d0, d1, …, dN-1 ]` where N is the number of branches.

| Index | Value | Register purpose |
|---|---|---|
| 0…N-1 | `Delays[i]` | Explicit delay (in symbols) for branch *i* |

Unlike `SimpleInterleaverProfile`, no separate branch count register is emitted — the register count itself implicitly determines the number of branches.

## Register Summary

| Profile | `Kind` | Register layout | Min registers | Max registers |
|---|---|---|---|---|
| `SimpleInterleaverProfile` | `"simple"` | `[ BranchCount, DelayStepSymbols ]` | 2 | 2 |
| `TableInterleaverProfile` | `"table"` | `[ delay₀, delay₁, …, delayₙ₋₁ ]` | 2 | 32 |

## Usage Site

**Source:** `src/Interleaver.Transport/ProfileUsageExample.cs:5`

```csharp
public static Task<bool> ConfigureDefaultAsync(
    DeviceController controller, CancellationToken cancellationToken = default)
{
    var profile = new SimpleInterleaverProfile(branchCount: 4, delayStepSymbols: 8);
    return controller.ApplyInterleaverProfile(profile, cancellationToken);
}
```

`DeviceController.ApplyInterleaverProfile` (`DeviceController.cs:10`) consumes the profile:

1. Calls `profile.ToRegisters()` to obtain the register array.
2. Compares against the last-applied registers; skips the write if they are identical (returns `false`).
3. Calls `_transport.WriteAsync(0x42, registers, cancellationToken)` to send command `0x42` plus the register payload to the hardware via the `IRegisterTransport` abstraction.

## Unknowns

- **Hardware semantics of each register value.** The repository defines the encoding format but does not document how the device interprets individual register values.
- **Upper bound on `DelayStepSymbols`.** Only a non-negative check exists; no explicit maximum is enforced in software.
- **Upper bound on individual delay values in `TableInterleaverProfile`.** Similarly unconstrained beyond non-negativity.
- **Behaviour when the transport write fails.** `DeviceController` propagates the exception but provides no retry or rollback logic.
- **Any additional profiles beyond the two concrete implementations documented here.** A thorough search of `src/` found only `SimpleInterleaverProfile` and `TableInterleaverProfile`.
