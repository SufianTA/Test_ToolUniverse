import streamlit as st
from generate_and_test_mcp_calls import run_all_tool_tests_streaming

st.set_page_config(layout="wide")
st.title("ToolUniverse Testing Dashboard")

status_icons = {
    "success": "✅",
    "error": "❌",
    "unknown": "🤷"
}

# --- Top Row: Search + Button ---
top_col1, top_col2 = st.columns([5, 1])
with top_col1:
    search_query = st.text_input(" ", placeholder="🔍 Filter by tool name or type...", key="search")  # No label
with top_col2:
    st.markdown("<div style='padding-top: 1.7rem'></div>", unsafe_allow_html=True)
    run_tests = st.button("Run MCP Tool Tests", use_container_width=True)

# --- Results Container ---
output_container = st.container()

if run_tests:
    st.session_state.results = []
    output_container.empty()

    with st.spinner("Running MCP tool tests..."):
        for result in run_all_tool_tests_streaming():
            st.session_state.results.append(result)

            if search_query:
                if search_query.lower() not in result["name"].lower() and search_query.lower() not in result.get("type", "").lower():
                    continue

            status = result.get("status", "unknown")
            icon = status_icons.get(status, "❔")

            with output_container.expander(
                f"{icon} `{result['name']}` ({result.get('type', 'N/A')}) - Status: {status.upper()}",
                expanded=False
            ):
                st.markdown(f"**📝 Description:** {result.get('description', '')}")
                st.markdown("**📥 Parameters:**")
                st.json(result.get("parameters", {}))
                st.markdown("**📤 Sample Input Sent:**")
                st.json(result.get("input", {}))
                st.markdown("**📄 Raw MCP Output:**")
                st.code(result.get("output", ""), language="json")

    st.success(f"✅ Finished testing {len(st.session_state.results)} tools.")

elif "results" in st.session_state:
    output_container.empty()
    for result in st.session_state.results:
        if search_query:
            if search_query.lower() not in result["name"].lower() and search_query.lower() not in result.get("type", "").lower():
                continue

        status = result.get("status", "unknown")
        icon = status_icons.get(status, "❔")

        with output_container.expander(
            f"{icon} `{result['name']}` ({result.get('type', 'N/A')}) - Status: {status.upper()}",
            expanded=False
        ):
            st.markdown(f"**📝 Description:** {result.get('description', '')}")
            st.markdown("**📥 Parameters:**")
            st.json(result.get("parameters", {}))
            st.markdown("**📤 Sample Input Sent:**")
            st.json(result.get("input", {}))
            st.markdown("**📄 Raw MCP Output:**")
            st.code(result.get("output", ""), language="json")
