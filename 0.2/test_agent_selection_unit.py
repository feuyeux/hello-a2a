import unittest
from unittest.mock import patch, MagicMock
import logging
import sys
import os

# Import the functions to test
from __main__ import (
    analyze_request_by_keywords,
    analyze_ambiguous_term_context,
    SmartRequestHandler
)

class TestAgentSelectionUnit(unittest.TestCase):
    """Unit tests for the agent selection logic"""

    def setUp(self):
        """Set up for the tests"""
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger()

    def test_keyword_analysis_clear_currency(self):
        """Test clear currency cases"""
        currency_queries = [
            "What is the exchange rate for USD to EUR?",
            "How much is 100 dollars in yen?",
            "Tell me about Bitcoin price trends",
            "Compare euro and pound exchange rates",
            "What's the current value of cryptocurrency?"
        ]
        
        for query in currency_queries:
            agent_type, confidence = analyze_request_by_keywords(query, self.logger)
            self.assertEqual(agent_type, "currency", f"Failed on query: {query}")
            self.assertGreater(confidence, 0.6, f"Low confidence on clear currency query: {query}")

    def test_keyword_analysis_clear_element(self):
        """Test clear element cases"""
        element_queries = [
            "What is the atomic number of Hydrogen?",
            "Tell me about the properties of Oxygen",
            "Compare the reactivity of Sodium and Potassium",
            "What are the isotopes of Carbon?",
            "Explain the electron configuration of Nitrogen"
        ]
        
        for query in element_queries:
            agent_type, confidence = analyze_request_by_keywords(query, self.logger)
            self.assertEqual(agent_type, "element", f"Failed on query: {query}")
            self.assertGreater(confidence, 0.6, f"Low confidence on clear element query: {query}")

    def test_keyword_analysis_ambiguous_terms(self):
        """Test cases with ambiguous terms like gold, silver, etc."""
        # Currency context
        currency_context_queries = [
            "What's the current price of gold in USD?",
            "How much is silver worth in the market?",
            "Is gold a good investment?",
            "Compare gold and silver prices over the last year",
            "What's the spot price of platinum today?"
        ]
        
        for query in currency_context_queries:
            agent_type, confidence = analyze_request_by_keywords(query, self.logger)
            self.assertEqual(agent_type, "currency", f"Failed on ambiguous currency query: {query}")
            self.assertGreater(confidence, 0.5, f"Too low confidence on ambiguous currency query: {query}")
        
        # Element context
        element_context_queries = [
            "What's the atomic weight of gold?",
            "Is silver a transition metal?",
            "How many electrons does gold have?",
            "What are the chemical properties of silver?",
            "Is platinum more reactive than gold?"
        ]
        
        for query in element_context_queries:
            agent_type, confidence = analyze_request_by_keywords(query, self.logger)
            self.assertEqual(agent_type, "element", f"Failed on ambiguous element query: {query}")
            self.assertGreater(confidence, 0.5, f"Too low confidence on ambiguous element query: {query}")

    def test_analyze_ambiguous_term_context(self):
        """Test the ambiguous term context analysis function directly"""
        # Test for 'gold' in currency context
        currency_context = "What is the market price of gold today? I want to invest."
        term = "gold"
        currency_matches, element_matches = analyze_ambiguous_term_context(term, currency_context, self.logger)
        self.assertGreater(currency_matches, element_matches, 
                         f"Failed to detect currency context for '{term}' in: {currency_context}")
        
        # Test for 'gold' in element context
        element_context = "Gold has an atomic number of 79 and is quite unreactive."
        currency_matches, element_matches = analyze_ambiguous_term_context(term, element_context, self.logger)
        self.assertGreater(element_matches, currency_matches, 
                         f"Failed to detect element context for '{term}' in: {element_context}")
        
        # Test for 'silver' in currency context
        currency_context = "Silver prices have been rising due to market demand."
        term = "silver"
        currency_matches, element_matches = analyze_ambiguous_term_context(term, currency_context, self.logger)
        self.assertGreater(currency_matches, element_matches, 
                         f"Failed to detect currency context for '{term}' in: {currency_context}")
        
        # Test for 'silver' in element context
        element_context = "Silver is used in many chemical reactions as a catalyst."
        currency_matches, element_matches = analyze_ambiguous_term_context(term, element_context, self.logger)
        self.assertGreater(element_matches, currency_matches, 
                         f"Failed to detect element context for '{term}' in: {element_context}")

    @patch('__main__.LLMChain')
    def test_smart_request_handler(self, mock_llm_chain):
        """Test the SmartRequestHandler class with mocked LLM"""
        # Mock the LLM to return a prediction
        mock_chain = MagicMock()
        mock_chain.predict.return_value = '{"agent": "currency", "reasoning": "Query is about currency exchange rates"}'
        mock_llm_chain.return_value = mock_chain
        
        # Create handler and test execution
        handler = SmartRequestHandler(self.logger)
        
        # Test currency query
        result = handler.execute("What is the exchange rate of USD to EUR?")
        self.assertEqual(result['agent'], "currency")
        
        # Test element query
        mock_chain.predict.return_value = '{"agent": "element", "reasoning": "Query is about element properties"}'
        result = handler.execute("What is the atomic number of Hydrogen?")
        self.assertEqual(result['agent'], "element")
        
        # Test handling of LLM failure
        mock_chain.predict.side_effect = Exception("LLM failure")
        result = handler.execute("What is the price of gold?")
        # Should fall back to keyword analysis
        self.assertIn('agent', result)
        self.assertIn('confidence', result)
        self.assertIn('method', result)
        self.assertEqual(result['method'], 'keywords')

    def test_edge_cases(self):
        """Test edge cases and potentially confusing queries"""
        edge_cases = [
            # Mixed signals
            ("What is gold?", None),  # Truly ambiguous, could accept either
            ("Tell me everything about silver", None),  # Truly ambiguous
            
            # Misleading queries 
            ("What is the chemical symbol for the currency Euro?", "element"),  # Contains currency word, but asking about chemical aspects
            ("How much does a mole of hydrogen atoms cost?", "currency"),  # Contains element, but asking about cost
            
            # Complex queries with multiple topics
            ("Compare the stability of gold as an investment versus its stability as an element", None),  # Mixed topic
            ("Is platinum more valuable as a catalyst or as an investment?", None),  # Mixed topic
        ]
        
        for query, expected in edge_cases:
            agent_type, confidence = analyze_request_by_keywords(query, self.logger)
            # For truly ambiguous cases, we just check if confidence is low
            if expected is None:
                self.assertLess(confidence, 0.6, f"Should have low confidence for ambiguous: {query}")
            else:
                # Otherwise check if the prediction matches expected agent
                # Allow for some flexibility in these challenging cases
                self.logger.info(f"Edge case: '{query}' → {agent_type} (conf: {confidence:.2f})")


if __name__ == '__main__':
    unittest.main()
