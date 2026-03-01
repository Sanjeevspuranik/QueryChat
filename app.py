import streamlit as st
import matplotlib.pyplot as plt
from graph import build_graph

st.set_page_config(page_title="QueryChat Graph", page_icon="📊")

st.title("📊 QueryChat")

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Ask about your database...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            result = st.session_state.graph.invoke(
                {"question": user_input}  # type: ignore
            )

            answer = result.get("answer", "No response.")
            df = result.get("dataframe")

            st.markdown(answer)

            # ---- Minimal Visualization ----
            if df is not None and not df.empty and df.shape[1] == 2:

                col1, col2 = df.columns

                fig, ax = plt.subplots()
                ax.bar(df[col1], df[col2])
                ax.set_xlabel(col1)
                ax.set_ylabel(col2)

                st.pyplot(fig)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer}
    )
