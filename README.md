# 🚀 QueryChat: Agentic NL-to-SQL System

QueryChat is a professional-grade Natural Language to SQL (NL-to-SQL) system built using **LangGraph** and an intelligent SQL agent. It transforms complex natural language questions into precise SQL queries, executes them against a relational database, and returns human-readable results through a modular, graph-based pipeline.

This project is designed for high-performance data interaction, experimentation, and demonstrating end-to-end AI agent workflows.

---

## 🎥 Watch the Demo

See QueryChat in action:

<video src="https://github.com/user-attachments/assets/47841152-1b70-4bbe-98fc-d0ea1c0f8023" controls="controls" style="max-width: 100%;">
  Your browser does not support the video tag.
</video>

_If the video does not load, you can [view it directly here](https://github.com/user-attachments/assets/47841152-1b70-4bbe-98fc-d0ea1c0f8023)._

---

## ✨ Key Features

- **Natural Language Interface**: Ask questions in plain English; get structured data in return.
- **Agentic Logic**: Powered by **LangGraph** for a controllable, stateful execution flow.
- **SQL Generation & Validation**: Sophisticated LLM prompting to ensure valid SQL syntax across tables.
- **Autonomous Execution**: Integrated execution engine that connects directly to your database.
- **Flexible Database Support**: Default support for **SQLite (Chinook DB)**, with easy extensibility to PostgreSQL or MySQL via SQLAlchemy.
- **Interactive UI**: Built with **Streamlit** for a seamless, chat-like user experience.

---

## 🏗 Architecture & Workflow

QueryChat utilizes a directed acyclic graph (DAG) to manage the reasoning process:

1. **State Initialization**: Captures user intent and relevant schema context.
2. **SQL Generation Node**: The LLM analyzes the schema and writes the optimized query.
3. **Execution Node**: The system runs the query and captures results (or handles errors).
4. **Response Synthesis**: Results are formatted into a natural language summary for the user.

---

## 📂 Project Structure

```text
QueryChat/
├── app.py                # Streamlit Frontend & UI logic
├── graph.py              # LangGraph Agent state and node definitions
├── chinook.db            # Sample SQLite Database for testing
├── requirements.txt      # Project Dependencies
├── .env                  # Environment Variables (User Created)
├── README.md             # Documentation
└── demo/
    └── QueryChat_demo.mp4 # Video Demonstration

```

---

## ⚙️ Setup & Installation

### 1️⃣ Clone the Repository

```bash
git clone [https://github.com/Sanjeevspuranik/QueryChat.git](https://github.com/Sanjeevspuranik/QueryChat.git)
cd QueryChat

```

### 2️⃣ Create a Virtual Environment

```bash
# Create environment
python -m venv venv

# Activate for Mac/Linux:
source venv/bin/activate

# Activate for Windows:
venv\Scripts\activate

```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt

```

### 4️⃣ Configure Environment

Create a `.env` file in the root directory and add your credentials:

```env
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=sqlite:///chinook.db

```

### 5️⃣ Run the Application

```bash
streamlit run app.py

```

---

## 🧪 Example Queries to Try

* *"Which artist has the most tracks in the database?"*
* *"What is the total revenue generated in 2023?"*
* *"Which country has the highest number of customers?"*
* *"Show me the top 5 most expensive tracks and their composers."*

---

## 🧠 Tech Stack

| Component | Technology |
| --- | --- |
| **Orchestration** | [LangGraph](https://github.com/langchain-ai/langgraph) |
| **LLM Framework** | [LangChain](https://github.com/langchain-ai/langchain) |
| **AI Model** | OpenAI GPT-4o / GPT-3.5-Turbo |
| **Database** | SQLite & SQLAlchemy |
| **Frontend** | Streamlit |

---

## 📄 License

This project is open-source and available under the [MIT License](https://www.google.com/search?q=LICENSE).

---

*Built for structured NL-to-SQL experimentation and Agentic AI research.* 🚀
