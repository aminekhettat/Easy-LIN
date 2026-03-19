# Easy-LIN

Easy-LIN is an open-source tool designed to work with the **LIN (Local Interconnect Network)** bus protocol. It provides the following capabilities:

- **LDF File Interpreter**: Parse and interpret LIN Description Files (LDF) to extract network topology, signals, frames, schedules, and node configurations as defined by the LIN specification.
- **LDF Consistency Checker**: Validate LDF files and check their internal consistency, detecting errors or mismatches in signal lengths, frame sizes, schedule tables, and node attributes before deployment.
- **Real-Time LIN Communication**: Connect to a LIN bus in real time using **Vector CANcase XL** and compatible Vector interfaces, enabling live signal monitoring, frame transmission, and schedule execution with a target product.
- **Extensible Hardware Support**: Additional USB LIN interface boxes and adapters will be integrated step by step as the project evolves.

## Features

- Parse and display the full content of LDF files
- Validate LDF consistency (signal ranges, frame payloads, schedule entries, etc.)
- Send and receive LIN frames in real time via Vector hardware
- Interactive schedule table execution
- Planned support for further USB LIN hardware devices

## License

This project is source-available. See the [LICENSE](LICENSE) file for full terms.  
In short: you may view and use the code for personal, non-commercial purposes, but redistribution and use in commercial projects are **not permitted** without prior written permission from the author.

## Contributing

Contributions, bug reports, and feature requests are welcome. Please open an issue or a pull request on [GitHub](https://github.com/aminekhettat/Easy-LIN).

