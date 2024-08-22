# Invoice Knowledge Graph Analysis System

This system allows users to convert their cloud-based invoices into a personal invoice knowledge graph and analyze their financial situation using natural language queries.

## Features

- Convert cloud-based invoices into a knowledge graph
- Utilize Neo4j as the knowledge graph database
- Support natural language queries for invoice data analysis
- Leverage GPT to transform natural language into Cypher query statements
- Use Claude 3.5 for final financial analysis and conclusions

## System Requirements

- Python 3.7+
- Neo4j database
- OpenAI GPT API key
- Anthropic Claude API key

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/LeoTW2/Invoice_Report_KG_RAG.git
   cd Invoice_Report_KG_RAG
   ```

2. Install required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up your Neo4j database

4. Configure environment variables:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `ANTHROPIC_API_KEY`: Your Anthropic API key
   - `NEO4J_URI`: Your Neo4j database URI
   - `NEO4J_USERNAME`: Neo4j username
   - `NEO4J_PASSWORD`: Neo4j password

## Usage

1. Prepare your invoice data and place it in the `data` folder (refer to the provided example data)

2. Run the system API:
   ```
   python main_api.py
   ```

3. Use the API endpoints for queries and analysis

## API Endpoints

Please put your api key(claude, gpt, neo4j) in invoice_analysor.py

## Example Data

Example invoice data is provided in the `data` folder for reference and testing purposes.

## Notes

- Ensure secure storage of your API keys and database credentials
- This system requires users to provide and manage their own Neo4j database
- Please adhere to the terms of service of the relevant service providers when using the APIs

## Contributing

Issues and pull requests are welcome to improve this project.

## License
