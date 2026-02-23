# -*- coding: utf-8 -*-
"""
Memgraph AI Query Interface with Streamlit
Created on Fri Feb 20 09:12:54 2026
"""

import streamlit as st
import mgclient
import threading
from langchain_anthropic import ChatAnthropic
from langchain_memgraph.toolkits import MemgraphToolkit
from langchain_memgraph.graphs.memgraph import MemgraphLangChain
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

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

        # Initialize Claude
        status.update(label="Initializing Claude...")
        log_step("1) Initializing Claude client")
        model = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=ANTHROPIC_API_KEY)

        # Verify Claude connection (short timeout)
        status.update(label="Verifying Claude connection...")
        log_step("2) Verifying Claude connection")
        run_with_timeout("Claude check", lambda: model.invoke("Ping"), 8)
        log_step("   Claude check passed")

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
        toolkit = MemgraphToolkit(db=db, llm=model)
        tools = toolkit.get_tools()
        tools = [tool for tool in tools if tool.name not in ["show_schema_info"]]
        log_step(f"   Loaded {len(tools)} tools")
        
        tool_names = [tool.name for tool in tools]
        list_of_tools = ', '.join(tool_names)
        
        # Create prompt template
        template = '''Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:
    
Information:  Do not use GROUP BY in the final cypher statement
Participant age is stored as age_at_enrollment
Cancer Type is stored in primary_disease_site


Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Output: Create a nice table displaying the results

Begin!

Question: {input}
Thought:{agent_scratchpad}'''
        
        prompt = PromptTemplate.from_template(template)
        agent = create_react_agent(model, tools, prompt)
        
        agent_executor = AgentExecutor(
            agent=agent, 
            tools=tools, 
            verbose=True, 
            handle_parsing_errors=True,
            return_intermediate_steps=True, 
            tool_choice="auto",
            max_iterations=5
        )
        
        status.update(label="Ready!", state="complete")
        log_step("6) Initialization complete")
        return {
            "executor": agent_executor,
            "tool_names": tool_names
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
    - `What is the total count of participants in the database?`
    - `Show me participants with lung cancer`
    - `Give me a breakdown of participants by gender`
    - `What studies are in the database?`
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
        with st.spinner("🤔 Claude is thinking..."):
            response = agent_data["executor"].invoke({
                "input": user_query
            })
        
        st.success("✅ Query completed!")
        
        # Tabs for results
        tab1, tab2, tab3 = st.tabs(["📝 Answer", "🔍 Steps", "📋 Raw"])
        
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
    
    except Exception as ex:
        st.error(f"❌ Error: {str(ex)}")

elif submit_button and not user_query:
    st.warning("⚠️ Please enter a query!")

# Sidebar
with st.sidebar:
    st.header("ℹ️ Info")
    st.markdown("""
    **Connection:**
    - Host: localhost:7687
    - Status: 🟢 Connected
    
    **Database Schema:**
    - Participant age: `age_at_enrollment`
    - Cancer Type: `primary_disease_site`
    """)
