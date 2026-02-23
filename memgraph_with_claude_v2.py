# -*- coding: utf-8 -*-
"""
Memgraph AI Query Interface with Streamlit
Created on Fri Feb 20 09:12:54 2026
"""

import streamlit as st
import mgclient
import threading
import json
from langchain_anthropic import ChatAnthropic
from langchain_memgraph.toolkits import MemgraphToolkit
from langchain_memgraph.graphs.memgraph import MemgraphLangChain
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain.tools import tool

# Streamlit Page Configuration
st.set_page_config(page_title="Memgraph AI Query Interface", page_icon="🧠", layout="wide")
st.title("AI Data Assistant Chatbot")
st.markdown("Ask questions about your graph database using natural language")

ANTHROPIC_API_KEY = "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"

@st.cache_resource
def initialize_memgraph_agent():
    """Initialize Memgraph connection and agent"""
    try:
        status = st.status("Starting checks...")
        log_lines = []

        def log_step(message):
            log_lines.append(message)
            st.write(message)

        def run_with_timeout(label, fn, timeout_seconds):
            result = {"error": None}

            def target():
                try:
                    fn()
                except Exception as exc:
                    result["error"] = exc

            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            thread.join(timeout_seconds)
            if thread.is_alive():
                raise TimeoutError(f"{label} timed out after {timeout_seconds}s")
            if result["error"]:
                raise result["error"]

        # Initialize Claude models
        status.update(label="Initializing Claude...")
        log_step("1) Initializing Claude clients")
        model_ids = [
            "claude-haiku-4-5-20251001",
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
        ]
        models = [ChatAnthropic(model=model_id, api_key=ANTHROPIC_API_KEY) for model_id in model_ids]

        # Verify Claude connection (short timeout)
        status.update(label="Verifying Claude connection...")
        log_step("2) Verifying Claude connections")
        for model_id, model in zip(model_ids, models):
            run_with_timeout(f"Claude check ({model_id})", lambda m=model: m.invoke("Ping"), 30)
        log_step("   Claude checks passed")

        # Connect to Memgraph
        status.update(label="Connecting to Memgraph...")
        log_step("3) Connecting to Memgraph (LangChain wrapper)")
        db = MemgraphLangChain(url="bolt://localhost:7687", username="", password="")

        # Verify Memgraph connection
        status.update(label="Verifying Memgraph connection...")
        log_step("4) Verifying Memgraph connection (mgclient)")

        def memgraph_check():
            conn = mgclient.connect(host="127.0.0.1", port=7687)
            cursor = conn.cursor()
            cursor.execute("MATCH (n) RETURN count(n) LIMIT 1")
            cursor.fetchall()

        run_with_timeout("Memgraph check", memgraph_check, 8)
        log_step("   Memgraph check passed")
        
        # Get toolkit
        status.update(label="Loading toolkit (this may take a moment)...")
        log_step("5) Loading Memgraph toolkit")
        toolkit = MemgraphToolkit(db=db, llm=models[0])

        @tool
        def show_schema_info_local():
            """Tool for showing schema information from Memgraph."""
            schema_info = db.query("SHOW SCHEMA INFO")
            return schema_info

        @tool
        def run_cypher(query: str):
            """Run a Cypher query against Memgraph."""
            return db.query(query)

        @tool
        def run_query(query: str):
            """Run a Cypher query against Memgraph (alias)."""
            return db.query(query)

        tools = toolkit.get_tools()
        tools = [tool for tool in tools if tool.name not in ["show_schema_info", "run_cypher", "run_query"]]
        tools.extend([show_schema_info_local, run_cypher, run_query])
        log_step(f"   Loaded {len(tools)} tools")
        
        tool_names = [tool.name for tool in tools]
        list_of_tools = ', '.join(tool_names)
        
        # Create prompt template
        template = '''You are an expert at translating user questions into Cypher. You have access to the following tools:

{tools}

Use the following format:
    
Information: Do not use GROUP BY in the final cypher statement
Participant age is stored as age_at_enrollment
Cancer Type is stored in primary_disease_site
Always call show_schema_info_local before writing Cypher.
Node labels are case-sensitive and MUST match the schema exactly.
Iterate up to 10 times: propose a Cypher query, run it, evaluate the result against the schema and the user question, then refine. Use the best final query.


Question: the input question you must answer
Thought: determine which schema elements are needed
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action. Evaluate whether the query matches the schema and answers the question.
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Output: Create a nice table displaying the results

Begin!

Question: {input}
Thought:{agent_scratchpad}'''
        
        prompt = PromptTemplate.from_template(template)
        executors = []
        for model in models:
            agent = create_react_agent(model, tools, prompt)
            executors.append(
                AgentExecutor(
                    agent=agent,
                    tools=tools,
                    verbose=True,
                    handle_parsing_errors=True,
                    return_intermediate_steps=True,
                    tool_choice="auto",
                    max_iterations=12,
                )
            )
        
        status.update(label="Ready!", state="complete")
        log_step("6) Initialization complete")
        return {
            "executors": executors,
            "tool_names": tool_names,
            "model": models[-1],
            "model_ids": model_ids
        }
        
    except Exception as e:
        st.error(f"❌ Initialization failed: {str(e)}")
        raise

# Initialize on startup
st.markdown("### Loading Memgraph Agent...")
try:
    agent_data = initialize_memgraph_agent()
    st.success("✅ Connected to Memgraph successfully!")
    st.info(f"🛠️ Available tools: {', '.join(agent_data['tool_names'])}")
except Exception as ex:
    st.error(f"Failed to connect: {str(ex)}")
    st.stop()

st.divider()

# Example queries
with st.expander("💡 Example Queries"):
    st.markdown("""
    - `How many nodes are in the database?`
    - `Show me all nodes and their relationships`
    - `What are the different node types?`
    - `Give me a summary of the database structure`
    - `List all nodes of a specific type and their properties`
    """)

# User input
user_query = st.text_area(
    "🔍 Enter your query:",
    placeholder="e.g., count of all participants",
    height=80,
    key="user_query_input"
)

col1, col2 = st.columns(2)
with col1:
    submit_button = st.button("🚀 Run Query", type="primary", use_container_width=True)
with col2:
    clear_button = st.button("🗑️ Clear", use_container_width=True)

if clear_button:
    st.rerun()

# Process query
if submit_button and user_query:
    st.divider()
    st.subheader("📊 Query Results")
    
    try:
        with st.spinner("🤔 Claude is thinking (3 models)..."):
            responses = []
            for executor in agent_data["executors"]:
                responses.append(
                    executor.invoke({
                        "input": user_query
                    })
                )

        def summarize_candidate(resp):
            steps = resp.get("intermediate_steps", [])
            last_cypher = ""
            for action, _ in steps:
                if action.tool in ["run_cypher", "run_query"]:
                    last_cypher = str(action.tool_input)
            return {
                "output": resp.get("output", ""),
                "last_cypher": last_cypher,
                "steps": len(steps)
            }

        candidates = [summarize_candidate(r) for r in responses]

        judge_prompt = (
            "You are grading 3 candidate answers to a graph database question. "
            "Pick the best one based on: schema compliance (case-sensitive labels), "
            "query correctness, and completeness. "
            "Return JSON only with keys: best_index (1-3) and reason.\n\n"
            f"User question: {user_query}\n\n"
            f"Candidate 1: {json.dumps(candidates[0], ensure_ascii=True)}\n"
            f"Candidate 2: {json.dumps(candidates[1], ensure_ascii=True)}\n"
            f"Candidate 3: {json.dumps(candidates[2], ensure_ascii=True)}\n"
        )

        best_index = 1
        judge_reason = ""
        try:
            judge_reply = agent_data["model"].invoke(judge_prompt)
            judge_text = judge_reply.content if hasattr(judge_reply, "content") else str(judge_reply)
            judge_data = json.loads(judge_text)
            best_index = int(judge_data.get("best_index", 1))
            judge_reason = str(judge_data.get("reason", ""))
        except Exception:
            best_index = 1

        best_index = max(1, min(3, best_index))
        response = responses[best_index - 1]
        
        st.success("✅ Query completed!")
        
        if judge_reason:
            model_label = agent_data.get("model_ids", ["model"] * 3)[best_index - 1]
            st.info(f"Selected model {best_index} ({model_label}) as best: {judge_reason}")

        # Tabs for results
        tab1, tab2, tab3, tab4 = st.tabs(["📝 Answer", "🔍 Steps", "📋 Raw", "🧪 Candidates"])
        
        with tab1:
            st.markdown("### Final Answer")
            if 'output' in response:
                st.write(response['output'])
            else:
                st.write(str(response)[:1000])
        
        with tab2:
            st.markdown("### Reasoning Steps")
            if 'intermediate_steps' in response and response['intermediate_steps']:
                for i, (action, observation) in enumerate(response['intermediate_steps'], 1):
                    with st.expander(f"Step {i}: {action.tool}"):
                        st.code(str(action.tool_input))
                        st.write(str(observation)[:300])
            else:
                st.info("No steps available")
        
        with tab3:
            st.json(response)

        with tab4:
            st.markdown("### Candidate Responses")
            for idx, resp in enumerate(responses, 1):
                model_label = agent_data.get("model_ids", ["model"] * 3)[idx - 1]
                with st.expander(f"Candidate {idx} ({model_label})"):
                    st.write(resp.get("output", "(no output)"))
                    st.json({
                        "last_cypher": candidates[idx - 1]["last_cypher"],
                        "steps": candidates[idx - 1]["steps"],
                        "raw": resp
                    })
    
    except Exception as ex:
        st.error(f"❌ Error: {str(ex)}")

elif submit_button and not user_query:
    st.warning("⚠️ Please enter a query!")

# Sidebar
with st.sidebar:
    st.header("ℹ️ Database Info")
    st.markdown("""
    **Connection:**
    - Host: localhost:7687
    - Status: 🟢 Connected
    
    **How It Works:**
    1. Ask a natural language question
    2. Claude uses available tools to discover the database schema
    3. Claude constructs a schema-aware Cypher query
    4. Results are returned as a formatted table
    
    **Available Tools:**
    The agent has access to Memgraph tools for schema discovery and query execution. Schema information is discovered dynamically, not hardcoded.
    """)
