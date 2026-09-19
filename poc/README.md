# UnderCover on AWS: proof of concept

This folder proves the AWS route for the course: the UnderCover app on Lambda and the UnderCover Agent on Bedrock AgentCore, with Gateway, Policy and Memory. It is a scratch project, not course material.

## What is here

- `poc.ipynb`: who you are running as, a check of permissions, and what the account has spent.
- `server.py`: a first slice of the UnderCover app in FastAPI. The claims routes need an `X-API-Key` header that matches `UNDERCOVER_API_KEY`. Run it locally with `uv run uvicorn server:app --reload --env-file .env`.
- `lambda_deploy.ipynb`: makes the API key in `.env` the first time, builds `server.py` for Lambda, deploys it behind a Function URL with the key in the function's environment, tests it with and without the key, lists what exists in the account, then tears down what it made.
- `gateway.ipynb`: puts an AgentCore Gateway in front of the app. It stores the app's API key in AgentCore Identity, creates the gateway's role and the gateway with IAM auth, adds the app's OpenAPI document as a target, lists and calls the tools over MCP with signed requests, then adds a policy engine with a Cedar rule that stops any payout over $1,000, first in `LOG_ONLY` mode and then enforced. Its teardown leaves the Lambda app alone.
- `memory.ipynb`: AgentCore Memory. It loads the policy wording into a `/wording` namespace and searches it, then records a handler's conversation and shows the notes the memory's strategy keeps in that handler's own namespace.
- `undercover/`: the UnderCover Agent as an AgentCore CLI project (`agentcore create`). `app/undercover_agent/` has the agent, LangGraph on OpenRouter with the gateway's tools; `agentcore/agentcore.json` is the deployment config. Run it locally from `undercover/` with `agentcore dev --logs --skip-deploy`, and talk to it from a second terminal with `agentcore dev "Look up claim CLM-1002"`. Without `--skip-deploy`, `agentcore dev` deploys to AWS first.
- `runtime.ipynb`: deploys the UnderCover Agent to AgentCore Runtime with `agentcore deploy`, talks to it with boto3, reads its logs, then tears it down: the stack, the CLI's credential provider, the runtime's log group, the token vault back on the AWS key, and the CLI's KMS key scheduled for deletion. Removing the CDK bootstrap is a switch at the end.
- `undercover-course-policy.json`: the IAM policy described below.
- `w1d2.ipynb`: the Week 1 Day 2 lab. It loads the claims queue with `get_sample_data` from `sample_data.py` and puts each claim to a line-up of models through OpenRouter with structured outputs (Luna and Qwen at the `low` reasoning level, gpt-oss-20b at `medium` hosted and locally on Ollama, Luna at `medium`), scores the decisions against the handlers' and reports the cost. It then scores Luna at `medium` on the held-out claims, tries two optional extras (Terra at `high` and Jev) and ends with a LangChain `create_agent` agent that looks up the policy record with one tool and records its decision with another. `TINY = True` keeps five claims of each set. It needs `OPENROUTER_API_KEY` in `.env`, Ollama with `gpt-oss` for the local entry (the notebook makes a 32k context copy of it, `gpt-oss-32k`, through Ollama's API), and nothing from AWS.
- `ARCHIVE_w1d2_medium.ipynb` and `ARCHIVE_w1d2_high.ipynb`: earlier comparison copies of the prototype at the `medium` and the `high` reasoning level, superseded by the lab and kept for reference.

## The order

`lambda_deploy.ipynb`, then `gateway.ipynb`, then `runtime.ipynb`. `memory.ipynb` stands alone. Each lab tears down what it made and leaves the rest alone, so tear down in the reverse order.

Still to prove: Langfuse traces from inside Runtime, and an approval that pauses in one session and resumes in another through a Postgres checkpointer on Supabase.

## What you need

- An AWS account on the Paid plan. AgentCore is not available on the Free plan, so the account needs a card, and new accounts get $100 of credit that covers this many times over.
- The AWS CLI v2, Node 20 or later, and uv. Python 3.12 is pinned in this folder.

## Setting up permissions

The IAM user you work as needs one policy, `undercover-course-policy.json`. It is scoped to what the course touches: AgentCore, CloudFormation (which the AgentCore CLI deploys through), the CDK roles and buckets, Lambda functions named `undercover*`, IAM roles named `undercover*`, logs, the tag search used for teardown, and read access to budgets and costs.

Signed in to the console as the root user:

1. **IAM, Policies, Create policy.** Choose the JSON tab, replace the contents with `undercover-course-policy.json`, choose Next, name it `undercover-course` and create it. The editor validates the policy as you paste it.
2. **IAM, User groups, Create group.** Name it `undercover-course`, attach the `undercover-course` policy, add your IAM user. A group is easier to remove later than a policy attached straight to the user, but attaching it directly works too.
3. **Billing access for the cost cells.** In the account menu, Account, scroll to IAM user and role access to Billing information, choose Edit and activate it. Without this, IAM users cannot read budgets or costs no matter what their policy says.
4. **A budget alarm.** In Billing and Cost Management, Budgets, create a monthly cost budget of $10 with alerts at 50, 80 and 100 percent to your email. The notebook checks that one exists before it deploys anything.

If your IAM user has no access key yet: IAM, Users, your user, Security credentials, Create access key, choose Command Line Interface, then run `aws configure` with the key, `us-east-1` as the region and `json` as the output format.

Check it worked:

```bash
aws sts get-caller-identity
aws bedrock-agentcore-control list-agent-runtimes
```

The first prints your account and user. The second prints an empty list of runtimes, which means the policy is attached and AgentCore is reachable.

## What the policy does and does not cover

The first `agentcore deploy` bootstraps the AWS CDK in your account, which creates a small CloudFormation stack called `CDKToolkit` with a bucket, a container repository and a handful of roles. One of those roles is the one CloudFormation uses to create resources, and CDK gives it administrator access by default. That is how CDK works everywhere: your user stays scoped to the policy above, and deployments run through that role.

With an API key in the project, the AgentCore CLI creates an AWS KMS key on its first deploy and moves your account's AgentCore token vault onto it, and its CDK bootstrap creates a second key for the assets bucket. A KMS key costs $1 a month, charged by the hour. The teardown in `runtime.ipynb` moves the vault back to the AWS key before it schedules the first key's deletion, and removing the bootstrap takes care of the second. `agentcore deploy --dry-run` also creates a key, so skip the dry run.

The policy leaves out things the course does not use: Bedrock's own models (we use OpenRouter), Cognito (we use IAM auth), AgentCore's payments, harnesses and evaluators, and anything in a VPC.

If a step fails with `AccessDenied`, the message names the action. Add it to the matching statement in the policy, save, and rerun the step. The policy was written from the AgentCore CLI's published developer policy and its permissions guide, and the notebook is where any gap shows up.

## Teardown

Everything the proof of concept creates is named with the prefix `undercover` and tagged `project=undercover`, apart from what the AgentCore CLI names itself: the `AgentCore-undercover-default` stack, the `CDKToolkit` stack and the two KMS keys. The last section of each notebook finds what that notebook made by name, deletes it in order, and then searches again to show what is left.
