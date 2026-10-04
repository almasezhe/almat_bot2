from datetime import datetime, timezone

from database import supabase


def get_assignee_for_category(category_id: str):
    # Get queue members for this category
    queue_result = (
        supabase
        .table("category_queue_members")
        .select("member_id, position, priority")
        .eq("category_id", category_id)
        .eq("enabled", True)
        .order("position")
        .execute()
    )

    if not queue_result.data:
        return None

    queue_members = queue_result.data

    member_ids = [
        row["member_id"]
        for row in queue_members
    ]

    # Get members who are actually allowed to receive leads
    members_result = (
        supabase
        .table("team_members")
        .select("id, status, is_active, can_receive_leads")
        .in_("id", member_ids)
        .eq("is_active", True)
        .eq("can_receive_leads", True)
        .eq("status", "ONLINE")
        .execute()
    )

    eligible_ids = {
        member["id"]
        for member in members_result.data
    }

    eligible = [
        row
        for row in queue_members
        if row["member_id"] in eligible_ids
    ]

    if not eligible:
        return None

    #PRIORITY DISTRIBUTION
    priority_members = [
        row
        for row in eligible
        if row["priority"] > 0
    ]

    if priority_members:
        priority_members.sort(
            key=lambda row: (
                -row["priority"],
                row["position"]
            )
        )

        selected = priority_members[0]

        new_priority = selected["priority"] - 1

        (
            supabase
            .table("category_queue_members")
            .update({
                "priority": new_priority
            })
            .eq("category_id", category_id)
            .eq("member_id", selected["member_id"])
            .execute()
        )
        return selected["member_id"]

    # NORMAL DISTRIBUTION
    state_result = (
        supabase
        .table("category_queue_state")
        .select("last_position")
        .eq("category_id", category_id)
        .execute()
    )

    if state_result.data:
        last_position = state_result.data[0]["last_position"]
    else:
        last_position = 0

    eligible.sort(
        key=lambda row: row["position"]
    )

    selected = None

    # Find next position after last_position
    for row in eligible:
        if row["position"] > last_position:
            selected = row
            break

    # End of queue → wrap around
    if selected is None:
        selected = eligible[0]

    (
        supabase
        .table("category_queue_state")
        .upsert(
            {
                "category_id": category_id,
                "last_position": selected["position"],
            },
            on_conflict="category_id"
        )
        .execute()
    )

    return selected["member_id"]