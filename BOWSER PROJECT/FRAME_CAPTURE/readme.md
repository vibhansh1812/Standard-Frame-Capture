

  In the both codes of IP camera and FLIR camera the comparison between them are :-
  1. The Frame capture  connects two IP camers 
  A front camera 
  A top camera 
  Over RTSP streams using open CV (CV2) to grab the frames in real time

  2. Each camera runs in its own dedicated thread saving the latest frame(TMP.jpg) to its folder and a TMP subdirectory for quick access.

  3. A rotating log system records errors, warnings, and restarts while ensuring log files remain small.

  4. If a camera stops returning frames for more than 5 seconds, the system sets module_stop = True and halts, making it suitable for industrial monitoring where uptime is critical.

  5. The PPE detection logic then analyzes the captured frames but may encounter the "invalid index to scalar variable" error when indexing dictList.

  6. This happens if the code tries to access dictList[i] assuming i maps to a valid list or dictionary entry, but the actual element is a scalar (string, integer, None) or the index is out of range.

  7. In such cases, the correct key (such as defectBool) should be used instead of the loop index, and type checks should ensure only valid collections are indexed, preventing runtime failures.

  8. Enumerate(...) loop does not correspond to how the data is structured — for example, when dictList is keyed by defectBool (representing a detected person’s ID) instead of a simple numeric index. If the wrong key is used, Python raises the error because it cannot access a sub-element of a scalar.
  
  9. To resolve this, the developer must first verify the exact structure and type of dictList at runtime, ensuring that the correct indexing method is applied. Where necessary, type checks should confirm that the object being accessed is indeed a collection type before attempting to index it. This not only prevents runtime crashes but also ensures that PPE detection remains accurate and uninterrupted in real-time monitoring scenarios.