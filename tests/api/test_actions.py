def test_create_preview_action_persists_and_returns_preview_state(client):
    response = client.post(
        "/actions/preview",
        json={
            "action_type": "stub_email_draft",
            "title": "Draft follow-up email",
            "preview_payload": {
                "subject": "Follow-up",
                "to": ["demo@example.com"],
                "body": "Draft body here",
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "preview"
    assert body["action_type"] == "stub_email_draft"
    assert body["approved_at"] is None

    actions_response = client.get("/actions")
    assert actions_response.status_code == 200
    actions = actions_response.json()
    assert len(actions) == 1
    assert actions[0]["id"] == body["id"]


def test_approve_preview_action_updates_status_and_creates_audit_events(client):
    create_response = client.post(
        "/actions/preview",
        json={
            "action_type": "stub_calendar_event",
            "title": "Create planning block",
            "preview_payload": {
                "summary": "Planning block",
                "start": "2026-04-11T09:00:00Z",
                "end": "2026-04-11T09:30:00Z",
            },
        },
    )
    action_id = create_response.json()["id"]

    approve_response = client.post(f"/actions/{action_id}/approve")

    assert approve_response.status_code == 200
    approved_action = approve_response.json()
    assert approved_action["status"] == "approved"
    assert approved_action["approved_at"] is not None

    audit_response = client.get("/audit")
    assert audit_response.status_code == 200
    audit_events = audit_response.json()
    assert len(audit_events) == 2
    assert audit_events[0]["event_type"] == "action_approved"
    assert audit_events[0]["action_id"] == action_id
    assert audit_events[1]["event_type"] == "action_created"
    assert audit_events[1]["action_id"] == action_id

