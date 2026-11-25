import 'package:material_ui/material_ui.dart';

import 'features/system_status/presentation/system_status_screen.dart';

class ResumeEngineApp extends StatelessWidget {
  const ResumeEngineApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'resume-engine',
      theme: ThemeData(colorSchemeSeed: Colors.indigo),
      darkTheme: ThemeData(
        colorSchemeSeed: Colors.indigo,
        brightness: Brightness.dark,
      ),
      // go_router replaces this in M5, when there is more than one screen.
      home: const SystemStatusScreen(),
    );
  }
}
