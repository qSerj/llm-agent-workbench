# Interleaver Profiles

> Source files: `src/Interleaver.Core/IInterleaverProfile.cs`, `src/Interleaver.Core/SimpleInterleaverProfile.cs`, `src/Interleaver.Core/TableInterleaverProfile.cs`, `src/Interleaver.Transport/DeviceController.cs`, `src/Interleaver.Transport/ProfileUsageExample.cs`

## Public Abstraction

`IInterleaverProfile` (`IInterleaverProfile.cs:3`) is the sole public interface for all interleaver profiles. It defines:

- **`Kind`** (`string`, read-only) — Returns a constant string (`"simple"` for `SimpleInterleaverProfile`, `"table"` for `TableInterleaverProfile`).
- **`ToRegisters()`** (`IReadOnlyList<int>`) — Serialises the profile into a flat list of integer register values for the transport interface (`IRegisterTransport`).

All validation and encoding logic lives in the concrete implementations. The transport layer consumes profiles exclusively through this interface.

## Concrete Implementations

### 1. `SimpleInterleaverProfile`

**Source:** `src/Interleaver.Core/SimpleInterleaverProfile.cs:3`

A compact profile that parameterises an interleaver with two values: a `BranchCount` and a `DelayStepSymbols`.

| Property | Type | Description |
|---|---|---|
| `BranchCount` | `int` | Must be 2–16 (validated in constructor) |
| `DelayStepSymbols` | `int` | Must be ≥ 0 (validated in constructor) |
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
| 0 | `BranchCount` | First register value |
| 1 | `DelayStepSymbols` | Second register value |

### 2. `TableInterleaverProfile`

**Source:** `src/Interleaver.Core/TableInterleaverProfile.cs:3`

A flexible profile that stores an explicit delay table as an array of integer values.

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

Returns the delay array directly: `[ d0, d1, …, dN-1 ]` where N is the array length.

| Index | Value | Register purpose |
|---|---|---|
| 0…N-1 | `Delays[i]` | Delay value at index *i* |

Unlike `SimpleInterleaverProfile`, no separate branch count register is emitted — the delay array length is the only size constraint.

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
3. Calls `_transport.WriteAsync(0x42, registers, cancellationToken)` through the `IRegisterTransport` abstraction.

## Unknowns

- **Hardware semantics of each register value.** The repository defines the encoding format but does not document how the device interprets individual register values.
- **Purpose of `Kind` as a discriminator.** The interface declares `Kind` and implementations return `"simple"` or `"table"`, but no code in `src/` reads or dispatches on this value.
- **Semantics of `BranchCount`.** The code validates the range 2–16 but does not document what the value represents for the device.
- **Semantics of `DelayStepSymbols`.** The code validates `>= 0` but does not document the hardware meaning.
- **Semantics of individual delay values in `TableInterleaverProfile`.** Each value must be `>= 0` but the hardware meaning is not documented.
- **Upper bound on `DelayStepSymbols`.** Only a non-negative check exists; no explicit maximum is enforced in software.
- **Upper bound on individual delay values in `TableInterleaverProfile`.** Similarly unconstrained beyond non-negativity.
- **Behaviour when the transport write fails.** `DeviceController` propagates the exception but provides no retry or rollback logic.
- **Any additional profiles beyond the two concrete implementations documented here.** A thorough search of `src/` found only `SimpleInterleaverProfile` and `TableInterleaverProfile`.
