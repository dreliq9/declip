package heimdall_state

import core "../core"

Id128 :: struct { high, low: u64 }
Project_Id   :: distinct Id128
Object_Id    :: distinct Id128
Revision_Id  :: distinct Id128
Snapshot_Id  :: distinct Id128
Candidate_Id :: distinct Id128
Branch_Id    :: distinct Id128

Hash256 :: struct { bytes: [32]u8 }
Revision_Ref :: struct { id: Revision_Id, hash: Hash256 }
Snapshot_Ref :: struct { id: Snapshot_Id, hash: Hash256 }

Object_Kind :: enum u16 { Invalid, Project, Sequence, Track, Clip, Asset_Ref, Transition, Audio_Route, Output_Intent }
Object_Ref :: struct { id: Object_Id, kind: Object_Kind }

Operation_Kind :: enum u16 { Invalid, Create_Project, Create_Sequence, Add_Track, Insert_Clip, Trim_Clip, Move_Clip, Split_Clip, Ripple_Delete, Set_Transition, Set_Audio_Route, Set_Output_Intent }
Precondition_Kind :: enum u16 { Invalid, Object_Exists, Object_Absent, Expected_Object_Hash, Expected_Branch_Head, Expected_Range }

Precondition :: struct {
    kind: Precondition_Kind,
    subject: Object_Ref,
    expected_hash: Hash256,
    expected_range: core.Time_Range,
}

Operation :: struct {
    operation_id: Id128,
    kind: Operation_Kind,
    target: Object_Ref,
    schema_version: u16,
    payload: []u8,
}

Candidate_Delta :: struct {
    id: Candidate_Id,
    project_id: Project_Id,
    base_revision: Revision_Ref,
    base_snapshot: Snapshot_Ref,
    operations: []Operation,
    preconditions: []Precondition,
    hash: Hash256,
}

Revision :: struct {
    id: Revision_Id,
    project_id: Project_Id,
    parents: []Revision_Ref,
    snapshot: Snapshot_Ref,
    candidate_delta_hash: Hash256,
    operation_batch_hash: Hash256,
    schema_version: u16,
}

Branch :: struct { id: Branch_Id, head: Revision_Ref }
Commit_Status :: enum i32 { Ok, Stale_Base, Branch_Head_Changed, Object_Not_Found, Object_Already_Exists, Object_Version_Mismatch, Precondition_Failed, Schema_Incompatible, Reference_Invalid, Transaction_Cancelled }

id128_is_zero :: proc(id: Id128) -> bool { return id.high == 0 && id.low == 0 }
hash256_is_zero :: proc(hash: Hash256) -> bool {
    for b in hash.bytes { if b != 0 { return false } }
    return true
}
