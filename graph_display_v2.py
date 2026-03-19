# -*- coding: utf-8 -*-
"""
Created on Thu Jan 29 10:42:59 2026

@author: breadsp2
"""

import streamlit as st
import pandas as pd
import mgclient as mgclient
import re
import os
import json
import httpx
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from streamlit_agraph import agraph, Node, Edge, Config
from langchain_openai import ChatOpenAI

from langchain_memgraph.graphs.memgraph import MemgraphLangChain
from langchain_memgraph.toolkits import MemgraphToolkit
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

pd.options.mode.chained_assignment = None

# Streamlit Page Configuration
# --- Streamlit UI ---

st.set_page_config(layout="wide")
st.set_page_config(page_title="Memgraph AI Query Interface", page_icon="🧠", layout="wide")

title_alignment = """
    <style>
    .centered-title {
        text-align: center;
    }
    </style>
"""

st.markdown(title_alignment, unsafe_allow_html=True)
st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0px; /* Adjust this value as needed */
            padding-left: 1rem;
            padding-right: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True)

st.markdown("""
<style>
.no-space {
    margin: 0;
    padding: 0;
    line-height: 0; /* Adjust as needed for minimal spacing */
}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='no-space' style='text-align: center; color: black; font-size: 30px; font-weight: bold;'>AI Data Assistant Chatbot</h1> " +
            "<p class='no-space' style='text-align: center; color: black; font-size: 15px;'>Ask questions about your graph database using natural language</p>",
             unsafe_allow_html=True)

# xAI API configuration
AIX_API_BASE_URL =  "https://api.x.ai/v1"
AIX_MODELS = [
    m.strip() for m in os.getenv(
        "AIX_MODELS",
        "grok-code-fast-1,grok-4-fast,grok-3-mini-fast"
    ).split(",") if m.strip()
]
AIX_JUDGE_MODEL = os.getenv("AIX_JUDGE_MODEL", "grok-4.20-beta-0309-reasoning")
AIX_INSECURE_SSL = os.getenv("AIX_INSECURE_SSL", "false").lower() == "true"
AIX_API_KEY = st.secrets['AIX_API_KEY']

if not AIX_API_KEY:
    st.error("Missing AIX_API_KEY environment variable.")
    st.stop()

if len(AIX_MODELS) < 1:
    st.error("No xAI generation models configured. Set AIX_MODELS.")
    st.stop()


def build_chat_model(model_name):
    return ChatOpenAI(
        model=model_name,
        api_key=AIX_API_KEY,
        base_url=AIX_API_BASE_URL,
        temperature=0,
        http_client=httpx.Client(verify=not AIX_INSECURE_SSL),
    )

class Memgraph_DB():
    def __init__(self):
        self.host = "127.0.0.1"
        self.port =  7687
        self.username = ""
        self.password = ""
    def connect_to_db(self): 
        self.conn = mgclient.connect(host=self.host, port=self.port, username=self.username, password=self.password)
        self.cursor = self.conn.cursor()

def get_memgraph_client():
    """Establishes and caches a connection to Memgraph."""
    mem_db = Memgraph_DB()
    try:
        mem_db.connect_to_db()
    except Exception as e:
        print(e)
        st.error(f"Error connecting to Memgraph: {e}")
        return None
    return mem_db

if "mem_db" not in st.session_state:
    st.session_state.mem_db = get_memgraph_client()

if st.session_state.mem_db is None:
    st.error("Memgraph is not reachable at 127.0.0.1:7687.")
    st.info("Start Memgraph first, then refresh this page.")
    st.stop()

if "db" not in st.session_state:
    memgraph_url = f"bolt://{st.session_state.mem_db.host}:{st.session_state.mem_db.port}"
    st.session_state.db = MemgraphLangChain(
        url=memgraph_url,
        username=st.session_state.mem_db.username,
        password=st.session_state.mem_db.password,
    )

def get_mem_tools(db):
    toolkit = MemgraphToolkit(db=db, llm=build_chat_model(AIX_MODELS[0]))
    tools = toolkit.get_tools()
    # Keep only run_cypher to avoid no-input tool signature issues with some model/agent combos.
    tools = [tool for tool in tools if tool.name == "run_cypher"]
    
    return tools

if "tools" not in st.session_state:
    st.session_state.tools = get_mem_tools(st.session_state.db)


def extract_cypher(output_str):
    """Extract a Cypher statement from model output."""
    if not output_str:
        return ""

    fenced_match = re.search(r"```(?:cypher)?\s*([\s\S]*?)\s*```", output_str, flags=re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1).strip()

    plain_match = re.search(r"(?is)\b(MATCH|WITH|UNWIND|CALL)\b[\s\S]*?(?:;|$)", output_str)
    if plain_match:
        return plain_match.group(0).strip().rstrip(";")

    return ""
    
if "list_of_tools" not in st.session_state:
    tool_names = [tool.name for tool in st.session_state.tools]
    st.session_state.list_of_tools = ', '.join(tool_names)

if "response" not in st.session_state:
    st.session_state.response = {}

if "result_summary" not in st.session_state:
    st.session_state.result_summary = ""

if "last_summary_query" not in st.session_state:
    st.session_state.last_summary_query = ""

if "last_user_query" not in st.session_state:
    st.session_state.last_user_query = ""

if "generation_models" not in st.session_state:
    st.session_state.generation_models = AIX_MODELS[:3]

if "judge_model_name" not in st.session_state:
    st.session_state.judge_model_name = AIX_JUDGE_MODEL

if "agent_executors" not in st.session_state:
    st.session_state.agent_executors = {}

if "model_runs" not in st.session_state:
    st.session_state.model_runs = {}

if "judge_decision" not in st.session_state:
    st.session_state.judge_decision = {}

if "property_value_hints" not in st.session_state:
    st.session_state.property_value_hints = ""


def build_node_property_value_hints(max_values_per_property=8):
    """Builds a compact catalog of node labels, properties, and example values."""
    query = """
    MATCH (n)
    UNWIND labels(n) AS label
    WITH label, n, keys(n) AS prop_keys
    UNWIND prop_keys AS prop
    RETURN label, prop, collect(DISTINCT toString(n[prop]))[0..$max_values] AS sample_values
    ORDER BY label, prop
    """

    catalog = {}
    try:
        st.session_state.mem_db.cursor.execute(query, {"max_values": int(max_values_per_property)})
        rows = st.session_state.mem_db.cursor.fetchall()
        for row in rows:
            label, prop, sample_values = row[0], row[1], row[2]
            if label not in catalog:
                catalog[label] = {}
            cleaned_values = []
            for value in (sample_values or []):
                value_str = str(value)
                if len(value_str) > 60:
                    value_str = value_str[:57] + "..."
                cleaned_values.append(value_str)
            catalog[label][prop] = cleaned_values
    except Exception:
        return "Property catalog unavailable."

    if not catalog:
        return "Property catalog unavailable."

    lines = [
        "Property Value Hints (use these labels/properties and value patterns when filtering):"
    ]
    for label in sorted(catalog.keys()):
        lines.append(f"- {label}")
        for prop in sorted(catalog[label].keys()):
            values = catalog[label][prop]
            preview = ", ".join(values) if values else "(no sample values)"
            lines.append(f"  - {prop}: {preview}")

    return "\n".join(lines)


def get_property_value_hints():
    """Returns cached property hints, rebuilding when missing."""
    if not st.session_state.property_value_hints:
        st.session_state.property_value_hints = build_node_property_value_hints()
    return st.session_state.property_value_hints

def create_agent(tools, llm, property_value_hints):
    template = '''You are an expert Open-Cypher data specialist who can generate complex queries based on user requirements to answer their questions using Open-Cypher.Answer the following questions as best you can in the form of a Cypher query. You have access to the following tools:
    
    {tools}
    
    Use the following format:
        
    Information:  Do not use GROUP BY in the final cypher statment
    Participant age is stored as age_at_enrollment
    Cancer Type is stored in primary_disease_site
    participant_id is stored in the participant node
    All nodes are lowercase and all relationships are lowercase
    Never use gender only use demographic.sex
    Don't use directional relationships in the cypher, the direction does not matter and can cause confusion for the model
    Stop using term and input the exact term asked for in the question when filtering, do not use a placeholder term

    {property_value_hints}
    
    Cypher Rules:
        when the variable is not a number then use the following filtering format WHERE ANY(term IN [term] WHERE tolower(variable) CONTAINS term) 
        lowercase all values expcet for the Cypher Key Words
        Only use enough tools to generate the Cypher
        Do no use " in the return statement, use ` instead

    
    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I now know the final answer and have the final cypher I need
    Final Answer: the final answer to the original input question
    
    Begin!
    
    Question: {input}
    Thought:{agent_scratchpad}'''
    prompt = PromptTemplate.from_template(template)
    prompt = prompt.partial(property_value_hints=property_value_hints)
    
    # xAI grok models can reject the OpenAI-style `stop` parameter; disable stop sequence injection.
    try:
        agent = create_react_agent(llm, tools, prompt, stop_sequence=False)  # Using ReAct pattern
    except TypeError:
        # Fallback for older langchain versions that don't expose stop_sequence.
        agent = create_react_agent(llm, tools, prompt)
    
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True,
                                   return_intermediate_steps=False, tool_choice="auto")
    return agent_executor


def get_or_create_agent_executor(model_name):
    if model_name not in st.session_state.agent_executors:
        llm = build_chat_model(model_name)
        property_value_hints = get_property_value_hints()
        st.session_state.agent_executors[model_name] = create_agent(
            st.session_state.tools,
            llm,
            property_value_hints,
        )
    return st.session_state.agent_executors[model_name]


def run_generation_models(user_query):
    generation_models = list(st.session_state.generation_models)

    # Build/cache executors first to avoid session-state races during parallel work.
    executors = {}
    for model_name in generation_models:
        executors[model_name] = get_or_create_agent_executor(model_name)

    def run_single_model(model_name):
        start_time = time.time()
        try:
            response = executors[model_name].invoke({"input": user_query})
            output_str = response.get("output", "") if isinstance(response, dict) else str(response)
            elapsed = time.time() - start_time
            return {
                "status": "ok",
                "response": response,
                "output": output_str,
                "cypher": extract_cypher(output_str),
                "error": "",
                "elapsed_seconds": round(elapsed, 2),
            }
        except Exception as e:
            elapsed = time.time() - start_time
            error_text = str(e)
            return {
                "status": "error",
                "response": {},
                "output": "",
                "cypher": extract_cypher(error_text),
                "error": error_text,
                "elapsed_seconds": round(elapsed, 2),
            }

    unordered_runs = {}
    max_workers = max(1, min(len(generation_models), 8))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(run_single_model, model_name): model_name
            for model_name in generation_models
        }
        for future in as_completed(future_map):
            model_name = future_map[future]
            try:
                unordered_runs[model_name] = future.result()
            except Exception as e:
                error_text = str(e)
                unordered_runs[model_name] = {
                    "status": "error",
                    "response": {},
                    "output": "",
                    "cypher": extract_cypher(error_text),
                    "error": error_text,
                }

    # Preserve display order configured in generation_models.
    return {model_name: unordered_runs.get(model_name, {
        "status": "error",
        "response": {},
        "output": "",
        "cypher": "",
        "error": "No result returned.",
    }) for model_name in generation_models}


def judge_best_cypher(user_query, model_runs):
    candidates = []
    for model_name, run_data in model_runs.items():
        if run_data.get("cypher"):
            candidates.append({"model": model_name, "cypher": run_data["cypher"]})

    if not candidates:
        return {
            "selected_model": "",
            "selected_cypher": "",
            "reason": "No model produced a Cypher query.",
        }

    if len(candidates) == 1:
        return {
            "selected_model": candidates[0]["model"],
            "selected_cypher": candidates[0]["cypher"],
            "reason": "Only one model produced Cypher.",
        }

    judge_prompt = f"""
You are a Cypher judge. Choose the best query for the user's question.

Question:
{user_query}

Candidates:
{json.dumps(candidates, indent=2)}

Return strict JSON only with keys: selected_model, selected_cypher, reason.
"""

    try:
        judge_model = build_chat_model(st.session_state.judge_model_name)
        judge_resp = judge_model.invoke(judge_prompt)
        judge_text = judge_resp.content if hasattr(judge_resp, "content") else str(judge_resp)
        json_match = re.search(r"\{[\s\S]*\}", judge_text)
        if not json_match:
            raise ValueError("Judge output was not valid JSON.")
        parsed = json.loads(json_match.group(0))
        return {
            "selected_model": parsed.get("selected_model", ""),
            "selected_cypher": parsed.get("selected_cypher", ""),
            "reason": parsed.get("reason", "Judge provided no reason."),
        }
    except Exception as e:
        return {
            "selected_model": candidates[0]["model"],
            "selected_cypher": candidates[0]["cypher"],
            "reason": f"Judge fallback used: {e}",
        }


def validate_cypher_against_schema(cypher, user_query):
    """Ask the judge model to verify the selected Cypher against the known schema and fix any mismatches."""
    if not cypher:
        return cypher, "No Cypher to validate."

    # Build schema description from session state
    schema_lines = []
    try:
        edge_df = st.session_state.final_df_edge
        if not edge_df.empty and {"child", "label", "parent"}.issubset(edge_df.columns):
            for _, row in edge_df[["child", "label", "parent"]].drop_duplicates().iterrows():
                schema_lines.append(f"  ({row['child']})-[:{row['label']}]->({row['parent']})")
    except Exception:
        pass

    schema_text = "\n".join(schema_lines) if schema_lines else "Schema unavailable."

    validation_prompt = f"""You are a Cypher validator for a graph database.

User question:
{user_query}

Known graph schema (node labels and relationship types):
{schema_text}

Cypher to validate:
{cypher}

Instructions:
1. Check that every node label used in the Cypher appears in the schema.
2. Check that every relationship type used in the Cypher appears in the schema.
3. If the Cypher is already correct for the schema, return it unchanged.
4. If there are label or relationship mismatches, fix them using the closest valid schema element.
5. Do not change query logic, only fix label/relationship names that deviate from the schema.

Return strict JSON only — no markdown, no extra text — with these keys:
- is_valid: boolean
- corrected_cypher: the corrected (or original if valid) Cypher string
- validation_notes: one-sentence description of issues found and corrections made, or "Query matches schema." if valid
"""

    try:
        judge_model = build_chat_model(st.session_state.judge_model_name)
        resp = judge_model.invoke(validation_prompt)
        resp_text = resp.content if hasattr(resp, "content") else str(resp)
        json_match = re.search(r"\{[\s\S]*\}", resp_text)
        if not json_match:
            raise ValueError("Validation output was not valid JSON.")
        parsed = json.loads(json_match.group(0))
        corrected = parsed.get("corrected_cypher", cypher).strip()
        notes = parsed.get("validation_notes", "")
        return corrected, notes
    except Exception as e:
        return cypher, f"Schema validation skipped: {e}"


MAX_REPAIR_ATTEMPTS = 3


def explain_cypher(cypher):
    """Run EXPLAIN on the query. Returns (ok: bool, error_msg: str)."""
    try:
        st.session_state.mem_db.cursor.execute(f"EXPLAIN {cypher}")
        st.session_state.mem_db.cursor.fetchall()
        return True, ""
    except Exception as e:
        return False, str(e)


def repair_cypher_with_feedback(cypher, user_query, error_msg, attempt):
    """Ask the judge model to fix a Cypher query given a concrete Memgraph EXPLAIN error."""
    repair_prompt = f"""You are a Cypher repair agent for a Memgraph database.

The following Cypher query failed when validated with EXPLAIN (attempt {attempt}).

User question:
{user_query}

Failed Cypher:
{cypher}

Memgraph error:
{error_msg}

Instructions:
1. Fix only what the error message describes — syntax, unknown labels, wrong relationship types, invalid property access, etc.
2. Do not change the intent or structure of the query beyond what is necessary to fix the error.
3. Do not use GROUP BY.
4. Use ANY(term IN [value] WHERE tolower(variable) CONTAINS term) for string filters.
5. Do not use directional relationships.

Return strict JSON only — no markdown — with keys:
- repaired_cypher: the fixed Cypher string
- repair_notes: one sentence describing what was changed
"""
    try:
        judge_model = build_chat_model(st.session_state.judge_model_name)
        resp = judge_model.invoke(repair_prompt)
        resp_text = resp.content if hasattr(resp, "content") else str(resp)
        json_match = re.search(r"\{[\s\S]*\}", resp_text)
        if not json_match:
            raise ValueError("Repair output was not valid JSON.")
        parsed = json.loads(json_match.group(0))
        return parsed.get("repaired_cypher", cypher).strip(), parsed.get("repair_notes", "")
    except Exception as e:
        return cypher, f"Repair skipped: {e}"


def summarize_result_table(df, user_question, cypher_query):
    """Generate a concise interpretation of query results for the Summary tab."""
    row_count = len(df)
    column_names = list(df.columns)
    preview_records = df.head(20).to_dict(orient="records")

    summary_prompt = f"""
You are summarizing database query results for a user.

User question:
{user_question}

Cypher query used:
{cypher_query}

Result metadata:
- row_count: {row_count}
- columns: {column_names}

Result preview (up to first 20 rows):
{preview_records}

Write a short interpretation focused on what the table means for the user's question.
If there are zero rows, clearly say no records matched.
Do not output cypher.
"""

    try:
        summary_model = build_chat_model(st.session_state.judge_model_name)
        summary_resp = summary_model.invoke(summary_prompt)
        return summary_resp.content if hasattr(summary_resp, "content") else str(summary_resp)
    except Exception as e:
        return f"Unable to generate AI summary from result table: {e}"
    

def drop_date(node,date_str):
    if date_str in node.properties:
        node.properties.pop(date_str)
    return node

def get_graph_data():
    # Example Cypher query: adjust to your specific data model
    query = """
    MATCH (n)-[r]->(m)
    RETURN n, r, m
    """
    nodes = {}
    edges = []
    st.session_state.mem_db.cursor.execute(query)
    result = st.session_state.mem_db.cursor.fetchall()
#    columns = [desc.name for desc in mg.description]
#    df = pd.DataFrame(result, columns=columns)
    
    for record in result:
        n = record[0]  #['n']  
        m = record[2]  #['m']  
        r = record[1]  #['r']
        # Add nodes to a dictionary to avoid duplicates
        if n.id not in nodes:
            nodes[n.id] = {"id": n.id, "label": list(n.labels)[0], "properties": n.properties}
        if m.id not in nodes:
            nodes[m.id] = {"id": m.id, "label": list(m.labels)[0], "properties": m.properties}
   
        n = drop_date(n, "created")
        r = drop_date(r, "created")
        m = drop_date(m, "created")

        n = drop_date(n, "modified")
        r = drop_date(r, "modified")
        m = drop_date(m, "modified")

        
        # Add edges
        edges.append({"child": list(n.labels)[0], "source": n.id, "parent": list(m.labels)[0], "target": m.id, "label": r.type, "properties": r.properties})
        
    # Format data for the visualization component (usually list of nodes and edges)
    graph_data = {
        "nodes": list(nodes.values()),
        "edges": edges
    }
    return graph_data

def make_schema(node_df, edge_df):
    nodes_agraph = [Node(id=node_df.loc[node, "index"], label=node_df.loc[node, "label"], 
                      size=25, shape="dot", color = node_df.loc[node, "color"]) for node in node_df.index]
# color="#FF0000")) # Red
# color="#00FF00")) # Green
    
    edges_agraph = [Edge(source=edge_df.loc[edge, 'index_x'], target=edge_df.loc[edge, 'index_y'], 
                     label="") for edge in edge_df.index]
                     #label=final_df_edge.loc[edge, 'label']) for edge in final_df_edge.index]

    config = Config(height=300,  width=600, directed=True, fit=True,
                    nodeHighlightColor="#FFAE42", linkHighlightColor="#FFAE42",
                    displayNodeImage=True, enablePhysics=True , hierarchical=True,
                    nodeSpacing= 350, treeSpacing =  200, edgeMinimization = False,
                    direction = "LR", blockShifting = False
                    # Example of custom node/edge properties (adjust as needed)
                    # node_stable_colors=True, edge_stable_colors=True
                    )
#    with graph_window.container(border=True):
    return nodes_agraph, edges_agraph, config

if "cypher_str" not in st.session_state:
    st.session_state.cypher_str = ""

if "graph_data" not in st.session_state:
    st.session_state.graph_data = get_graph_data()
    z = pd.DataFrame(st.session_state.graph_data["nodes"])

    if not z.empty and "label" in z.columns:
        temp = {i: j for j, i in enumerate(set(z["label"]))}
        res = [temp[i] for i in z["label"]]
        for idx in range(0, len(res)):
            st.session_state.graph_data["nodes"][idx]["index"] = res[idx]
    elif z.empty:
        st.info("Memgraph connected, but no relationships were found for schema display.")
    else:
        st.warning("Graph nodes are missing the 'label' field required for schema visualization.")
  
if "node_df" not in st.session_state and "final_df_edge" not in st.session_state:
    st.session_state.node_df = pd.DataFrame(st.session_state.graph_data["nodes"])
    edge_df = pd.DataFrame(st.session_state.graph_data["edges"])

    if st.session_state.node_df.empty:
        st.session_state.node_df = pd.DataFrame(columns=["index", "label", "properties", "color"])
        st.session_state.final_df_edge = pd.DataFrame(columns=["child", "label", "parent", "index_x", "index_y"])
    else:
        if edge_df.empty:
            st.session_state.final_df_edge = pd.DataFrame(columns=["child", "label", "parent", "index_x", "index_y"])
        else:
            new_edges = edge_df.merge(st.session_state.node_df[["id", "index"]], left_on="source", right_on="id")
            new_edges = new_edges.merge(st.session_state.node_df[["id", "index"]], left_on="target", right_on="id")
            st.session_state.final_df_edge = new_edges.drop_duplicates(["index_x", "index_y"])
            st.session_state.final_df_edge.drop(["source", "target"], axis=1, inplace=True)
            st.session_state.final_df_edge["index_x"] = st.session_state.final_df_edge["index_x"].astype(str)
            st.session_state.final_df_edge["index_y"] = st.session_state.final_df_edge["index_y"].astype(str)

        st.session_state.node_df.drop_duplicates("index", inplace=True)
        st.session_state.node_df.drop("id", axis=1, inplace=True)
        st.session_state.node_df["index"] = st.session_state.node_df["index"].astype(str)
        st.session_state.node_df["color"] = "#87CEFA"   #blue nodes
        st.session_state.node_df.reset_index(inplace=True)

    
st.markdown("""
<style>
    /* Targets the label of the multiselect widget */
    .stMultiSelect > label {
        font-size: 12px; /* Adjust the size as needed */
        color: gray; /* Optional: change color */
    }

    /* Targets the text of the selected options inside the multiselect box */
    .stMultiSelect [data-baseweb="select"] span {
        font-size: 8px; /* Adjust the size as needed */
    }
</style>
""", unsafe_allow_html=True)



user_window = st.empty()
schema_col, user_col = st.columns([3, 2])

with schema_col:
    show_schema, schema_table = st.tabs(["Visualize Schema", "Schema as Table"])
            
    with show_schema:
        nodes_agraph, edges_agraph, config = make_schema(st.session_state.node_df, st.session_state.final_df_edge)
        agraph(nodes_agraph, edges_agraph, config)

    with schema_table:
        st.dataframe(st.session_state.final_df_edge[["child", "label", "parent"]])

with user_col:
    user_input, cypher_output = st.tabs(["User Query", "Cypher Code"])
    summary_tab = st.tabs(["Results"])[0]
    
    with user_input:
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
            
    if submit_button and user_query:
        st.divider()
        st.session_state.cypher_str = ""
        st.session_state.response = {}
        st.session_state.model_runs = {}
        st.session_state.judge_decision = {}
        st.session_state.result_summary = ""
        st.session_state.last_summary_query = ""
        st.session_state.last_user_query = user_query
        try:
            st.session_state.model_runs = run_generation_models(user_query)
            st.session_state.judge_decision = judge_best_cypher(user_query, st.session_state.model_runs)

            selected_cypher = st.session_state.judge_decision.get("selected_cypher", "")

            # Schema validation pass — judge reviews its own selection against actual schema
            if selected_cypher:
                validated_cypher, validation_notes = validate_cypher_against_schema(selected_cypher, user_query)
            else:
                validated_cypher, validation_notes = "", "No Cypher to validate."

            st.session_state.judge_decision["validated_cypher"] = validated_cypher
            st.session_state.judge_decision["validation_notes"] = validation_notes

            # Execution-feedback repair loop — EXPLAIN against live DB, repair on failure
            repair_log = []
            working_cypher = validated_cypher
            if working_cypher:
                for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                    ok, error_msg = explain_cypher(working_cypher)
                    if ok:
                        repair_log.append({"attempt": attempt, "status": "✅ EXPLAIN passed", "notes": ""})
                        break
                    repaired, notes = repair_cypher_with_feedback(working_cypher, user_query, error_msg, attempt)
                    repair_log.append({"attempt": attempt, "status": f"❌ EXPLAIN failed", "notes": f"{error_msg[:120]} → {notes}"})
                    working_cypher = repaired
                else:
                    # Final EXPLAIN after last repair attempt
                    ok, error_msg = explain_cypher(working_cypher)
                    if not ok:
                        repair_log.append({"attempt": MAX_REPAIR_ATTEMPTS + 1, "status": "⚠️ Could not fix after max attempts", "notes": error_msg[:120]})

            st.session_state.judge_decision["repair_log"] = repair_log
            st.session_state.cypher_str = working_cypher

            selected_model = st.session_state.judge_decision.get("selected_model", "")
            if selected_model and selected_model in st.session_state.model_runs:
                st.session_state.response = st.session_state.model_runs[selected_model].get("response", {})

            if st.session_state.cypher_str:
                passed = any("passed" in r["status"] for r in repair_log)
                label = "✅ Query generated, validated, and EXPLAIN-verified." if passed else "✅ Query generated and validated (EXPLAIN unavailable)."
                st.success(label)
            else:
                st.warning("No Cypher query was generated by the configured models.")

        except Exception as e:
            st.error(f"❌ Query failed: {e}")
            extracted_from_error = extract_cypher(str(e))
            if extracted_from_error:
                st.session_state.cypher_str = extracted_from_error
                st.warning("Cypher was extracted from an error path and is shown in the Cypher Code tab.")
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                st.info("xAI TLS verification failed in this environment. Set AIX_INSECURE_SSL=true for local testing.")
            
    
    with cypher_output:

        if st.session_state.cypher_str != "":
            st.write(st.session_state.cypher_str)

            pattern = r"([a-z]{1}:[a-z]+)"
            matches = re.findall(pattern, st.session_state.cypher_str)
            node_names = [i[2:] for i in matches]

            if node_names:
                x = st.session_state.node_df.query(f"label in {node_names}")
                st.session_state.node_df.loc[x.index, "color"] = "#00FF00"
        else:
            st.write("no cypher statement was created")
                
    with summary_tab:
        st.write("Summary")

        if st.session_state.model_runs:
            run_rows = []
            for model_name, run_data in st.session_state.model_runs.items():
                run_rows.append({
                    "model": model_name,
                    "status": run_data.get("status", ""),
                    "elapsed_time": f"{run_data.get('elapsed_seconds', 0)}s",
                    "has_cypher": bool(run_data.get("cypher")),
                    "error": run_data.get("error", "")[:140],
                })
            st.write("Model generation runs")
            st.dataframe(pd.DataFrame(run_rows), use_container_width=True)

        if st.session_state.judge_decision:
            with st.container(border=True):
                st.write("Judge selection")
                st.write(f"Selected model: {st.session_state.judge_decision.get('selected_model', 'n/a')}")
                st.write(st.session_state.judge_decision.get("reason", ""))
                validation_notes = st.session_state.judge_decision.get("validation_notes", "")
                if validation_notes:
                    st.write(f"Schema validation: {validation_notes}")
                repair_log = st.session_state.judge_decision.get("repair_log", [])
                if repair_log:
                    st.write("EXPLAIN repair log")
                    st.dataframe(pd.DataFrame(repair_log), use_container_width=True)

        if st.session_state.cypher_str != "":
            try:
                query = st.session_state.cypher_str.strip()
                st.session_state.mem_db.cursor.execute(query)
                result = st.session_state.mem_db.cursor.fetchall()
                columns = [desc.name for desc in st.session_state.mem_db.cursor.description]
                df = pd.DataFrame(result, columns=columns)

                if st.session_state.last_summary_query != query:
                    st.session_state.result_summary = summarize_result_table(
                        df=df,
                        user_question=st.session_state.last_user_query,
                        cypher_query=query,
                    )
                    st.session_state.last_summary_query = query
            except Exception as e:
                st.error(f"Cypher execution error: {e}")
                st.session_state.result_summary = f"Could not interpret results because query execution failed: {e}"
                df = pd.DataFrame()
        else:
            df = pd.DataFrame()

        with st.container(border=True):
            st.write("AI interpretation of result table")
            if st.session_state.result_summary:
                st.write(st.session_state.result_summary)
            else:
                st.write("Run a query to generate a summary from the Result Table.")

        st.write("Result Table")
        with st.container(border=True):
            if not df.empty:
                st.dataframe(df, use_container_width=True)
            else:
                st.write("no data to display")
                
            
                      
