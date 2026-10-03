"""What the test backend has recorded on a claim."""


def claim_of(client, claim_id):
    return client.get(f"/api/claims/{claim_id}").json()


def steps_of(client, claim_id):
    return client.get(f"/api/claims/{claim_id}/steps").json()
