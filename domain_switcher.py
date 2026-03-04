#!/usr/bin/env python3
"""
Domain Switcher Utility
Switch between different domains (education, banking, healthcare, etc.)

Usage:
    python domain_switcher.py                  # Interactive mode
    python domain_switcher.py --domain banking # Direct switch
    python domain_switcher.py --list           # List available domains
"""
import sys
import argparse
from pathlib import Path

from config.domains import AVAILABLE_DOMAINS, list_domains
from config import settings


def list_available_domains():
    """Display all available domains with their details"""
    print("\n" + "=" * 70)
    print("AVAILABLE DOMAINS")
    print("=" * 70)

    for domain_name, domain in AVAILABLE_DOMAINS.items():
        active = "✅ ACTIVE" if domain_name == settings.ACTIVE_DOMAIN else ""
        print(f"\n📦 {domain_name.upper()} {active}")
        print(f"   Description: {domain.description}")
        print(f"   Entity: {domain.entity_name} ({domain.entity_name_plural})")
        print(f"   CSV File: {domain.csv_file_path}")
        print(f"   Fields: {len(domain.fields)} ({', '.join(domain.field_names[:5])}...)")

        # Check if CSV exists
        csv_path = Path(domain.csv_file_path)
        if csv_path.exists():
            print(f"   Status: ✅ CSV file found")
        else:
            print(f"   Status: ⚠️  CSV file missing (create {domain.csv_file_path})")

        # Show example queries
        if domain.example_queries:
            print(f"   Example: \"{domain.example_queries[0]}\"")

    print("\n" + "=" * 70)


def switch_domain(domain_name: str):
    """
    Switch to a different domain

    Args:
        domain_name: Name of domain to switch to
    """
    try:
        # Validate domain exists
        if domain_name not in AVAILABLE_DOMAINS:
            print(f"\n❌ Error: Domain '{domain_name}' not found")
            print(f"Available domains: {', '.join(list_domains())}")
            return False

        domain = AVAILABLE_DOMAINS[domain_name]

        # Check if CSV file exists
        csv_path = Path(domain.csv_file_path)
        if not csv_path.exists():
            print(f"\n⚠️  Warning: CSV file not found: {domain.csv_file_path}")
            print(f"The system will not work until you create this file.")
            response = input(f"Continue anyway? (y/n): ")
            if response.lower() != 'y':
                return False

        # Perform switch
        settings.set_domain(domain_name)

        print(f"\n✅ Successfully switched to {domain_name.upper()} domain")
        print(f"   Entity: {domain.entity_name_plural}")
        print(f"   CSV: {domain.csv_file_path}")
        print(f"   Fields: {', '.join(domain.field_names)}")

        # Update environment (for persistence)
        print(f"\n💡 To make this permanent, set environment variable:")
        print(f"   export DOMAIN={domain_name}")
        print(f"   or add to your .env file: DOMAIN={domain_name}")

        return True

    except Exception as e:
        print(f"\n❌ Error switching domain: {e}")
        return False


def interactive_mode():
    """Interactive domain selection"""
    print("\n" + "🔄 DOMAIN SWITCHER" + "\n")

    current = settings.get_domain()
    print(f"Current domain: {settings.ACTIVE_DOMAIN} ({current.entity_name_plural})")

    print("\nSelect a domain:")
    domains = list(AVAILABLE_DOMAINS.keys())
    for i, domain_name in enumerate(domains, 1):
        domain = AVAILABLE_DOMAINS[domain_name]
        csv_exists = "✅" if Path(domain.csv_file_path).exists() else "⚠️ "
        active = "← CURRENT" if domain_name == settings.ACTIVE_DOMAIN else ""
        print(f"{i}. {csv_exists} {domain_name:12} - {domain.description:40} {active}")

    print(f"{len(domains) + 1}. Show detailed info")
    print(f"{len(domains) + 2}. Exit")

    try:
        choice = input(f"\nEnter choice (1-{len(domains) + 2}): ").strip()

        if not choice.isdigit():
            print("Invalid choice")
            return

        choice = int(choice)

        if choice == len(domains) + 1:
            list_available_domains()
            interactive_mode()  # Re-prompt
        elif choice == len(domains) + 2:
            print("Exiting...")
            return
        elif 1 <= choice <= len(domains):
            domain_name = domains[choice - 1]
            switch_domain(domain_name)
        else:
            print("Invalid choice")

    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"\nError: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Switch between different domain configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--domain', '-d',
        help='Domain name to switch to (education, banking, healthcare, etc.)'
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all available domains'
    )

    args = parser.parse_args()

    if args.list:
        list_available_domains()
    elif args.domain:
        switch_domain(args.domain)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
